import copy
import datetime as dt
import importlib.util
import json
from pathlib import Path
import plistlib
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("apple_preflight", ROOT / "tools/apple-preflight.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class ApplePreflightTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.config = json.loads((ROOT / "docs/launch/examples/isofall.apple-release.json").read_text())
        self.config["artifacts"]["archive"] = None
        (self.root / "Isofall.xcodeproj").mkdir()
        self.profile = {"TeamIdentifier": ["CUYMUDSGA4"],
                        "ExpirationDate": dt.datetime.now() + dt.timedelta(days=20),
                        "Entitlements": {"application-identifier": "CUYMUDSGA4.com.jamesktan.isofall", "get-task-allow": False}}
        self.info = {"CFBundleIdentifier": "com.jamesktan.isofall", "CFBundleVersion": "5",
                     "CFBundleShortVersionString": "1.0.0", "CFBundleSupportedPlatforms": ["iPhoneOS"]}
        self.write_ipa()

    def tearDown(self):
        self.directory.cleanup()

    def write_ipa(self):
        path = self.root / self.config["artifacts"]["ipa"]
        path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("Payload/Isofall.app/Info.plist", plistlib.dumps(self.info))
            archive.writestr("Payload/Isofall.app/embedded.mobileprovision", b"test profile")

    def execute(self, env=None):
        def command(argv, _env, data=None):
            if argv == ["xcodebuild", "-version"]:
                return subprocess.CompletedProcess(argv, 0, b"Xcode 26.6\nBuild version test", b"")
            self.assertEqual(argv, ["security", "cms", "-D"])
            self.assertEqual(data, b"test profile")
            return subprocess.CompletedProcess(argv, 0, plistlib.dumps(self.profile), b"")
        with patch.object(MODULE, "run", side_effect=command):
            return MODULE.assess(self.config, self.root, env or {})

    def test_development_export_is_not_distribution_ready(self):
        self.profile["Entitlements"]["get-task-allow"] = True
        report = self.execute()
        self.assertIn("distribution_profile", report["blocking_local_checks"])
        self.assertEqual(report["store_readiness"], "unverified")

    def test_local_pass_does_not_claim_store_access_or_publication(self):
        report = self.execute()
        self.assertEqual(report["local_status"], "passed")
        self.assertEqual(report["store_readiness"], "unverified")
        self.assertFalse(report["account_or_store_writes_performed"])
        self.assertEqual(next(c for c in report["checks"] if c["id"] == "account_session")["status"], "unknown")

    def test_review_requires_urls_but_draft_upload_does_not(self):
        self.assertNotIn("privacy_policy_url", self.execute()["blocking_local_checks"])
        self.config["release"]["goal"] = "submit_for_review"
        blockers = self.execute()["blocking_local_checks"]
        self.assertIn("privacy_policy_url", blockers)
        self.assertIn("support_url", blockers)
        self.assertIn("media_manifest", blockers)

    def test_wrong_bundle_or_simulator_ipa_is_rejected(self):
        self.info.update(CFBundleIdentifier="com.other.app", CFBundleSupportedPlatforms=["iPhoneSimulator"])
        self.write_ipa()
        blockers = self.execute()["blocking_local_checks"]
        self.assertIn("CFBundleIdentifier", blockers)
        self.assertIn("device_platform", blockers)

    def test_expired_and_wrong_team_profiles_are_rejected(self):
        self.profile.update(TeamIdentifier=["OTHERTEAM1"], ExpirationDate=dt.datetime(2020, 1, 1))
        blockers = self.execute()["blocking_local_checks"]
        self.assertIn("profile_team", blockers)
        self.assertIn("profile_expiry", blockers)

    def test_profile_classes_distinguish_non_store_exports(self):
        for extra, expected in [({"ProvisionedDevices": []}, "ad_hoc"), ({"ProvisionsAllDevices": True}, "enterprise")]:
            profile = {**self.profile, **extra}
            self.assertEqual(MODULE.profile_facts(profile)["kind"], expected)

    def test_inline_secret_fields_and_values_are_rejected(self):
        config = copy.deepcopy(self.config)
        config["access"]["private_key"] = "SECRET_SENTINEL"
        with self.assertRaises(ValueError):
            MODULE.validate(config)
        config = copy.deepcopy(self.config)
        config["access"]["key_path_env"] = "/private/key.p8"
        with self.assertRaises(ValueError):
            MODULE.validate(config)

    def test_key_reference_does_not_read_or_echo_key_material(self):
        with tempfile.TemporaryDirectory() as key_dir:
            key = Path(key_dir) / "key.p8"
            key.write_text("SECRET_SENTINEL")
            self.config["access"] = {"mode": "team_api_key", "key_path_env": "KEY_PATH", "key_id_env": "KEY_ID", "issuer_id_env": "ISSUER_ID"}
            with patch.object(Path, "read_bytes", side_effect=AssertionError("Must not read the private key")), patch.object(Path, "read_text", side_effect=AssertionError("Must not read the private key")):
                report = self.execute({"KEY_PATH": str(key), "KEY_ID": "PRIVATE_ID_SENTINEL", "ISSUER_ID": "PRIVATE_ISSUER_SENTINEL"})
            output = json.dumps(report)
            for hidden in ("SECRET_SENTINEL", "PRIVATE_ID_SENTINEL", "PRIVATE_ISSUER_SENTINEL", str(key)):
                self.assertNotIn(hidden, output)
            self.assertEqual(report["store_readiness"], "unverified")

    def test_archive_ignores_external_drive_metadata_sidecars(self):
        self.config["artifacts"]["archive"] = "build/Isofall.xcarchive"
        apps = self.root / "build/Isofall.xcarchive/Products/Applications"
        (apps / "Isofall.app").mkdir(parents=True)
        (apps / "._Isofall.app").write_bytes(b"AppleDouble sidecar")
        self.assertNotIn("archive", self.execute()["blocking_local_checks"])

    def test_key_in_enclosing_repository_is_rejected_for_nested_app(self):
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            for worktree in (False, True):
                with self.subTest(worktree=worktree):
                    marker = repository / ".git"
                    if worktree:
                        marker.write_text("gitdir: /elsewhere/worktrees/example")
                    else:
                        marker.mkdir()
                    self.root = repository / "apps/ios"
                    (self.root / "Isofall.xcodeproj").mkdir(parents=True, exist_ok=True)
                    self.write_ipa()
                    key = repository / "AuthKey.p8"
                    key.write_text("SECRET_SENTINEL")
                    self.config["access"] = {"mode": "individual_api_key", "key_path_env": "KEY_PATH", "key_id_env": "KEY_ID"}
                    report = self.execute({"KEY_PATH": str(key), "KEY_ID": "ID_SENTINEL"})
                    self.assertIn("key_storage", report["blocking_local_checks"])
                    if worktree:
                        marker.unlink()
                    else:
                        marker.rmdir()

    def test_scheduled_release_requires_an_explicit_timezone(self):
        self.config["release"].update(mode="scheduled", not_before="2026-11-01T10:00:00")
        with self.assertRaises(ValueError):
            MODULE.validate(self.config)
        self.config["release"]["not_before"] = "2026-11-01T10:00:00-08:00"
        MODULE.validate(self.config)

    def test_automatic_review_submission_flags_public_release_scope(self):
        self.config["release"].update(goal="submit_for_review", mode="automatic")
        report = self.execute()
        check = next(c for c in report["checks"] if c["id"] == "public_release_authorization")
        self.assertEqual(check["status"], "unknown")
        self.assertEqual(check["next_actor"], "owner")


if __name__ == "__main__":
    unittest.main()
