"""Offline fixtures for portable, read-only project resume discovery."""
import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.dont_write_bytecode = True
HELPER = Path(__file__).resolve().parents[1] / "docs/launch/harness/deploy/shippykit.py"
SPEC = importlib.util.spec_from_file_location("shippykit_resume", HELPER)
resume = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(resume)


def write(root, name, value="fixture"):
    target = root / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(value, encoding="utf-8")
    return target


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def tree(root):
    return {str(p.relative_to(root)): ("link", os.readlink(p)) if p.is_symlink() else ("dir",) if p.is_dir() else ("file", p.read_bytes()) for p in root.rglob("*")}


class ResumeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="shippykit-resume-test-")
        self.root = Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)

    def status(self, hashes=False):
        # Most cases need no git subprocess; source behavior has its own fixture.
        with mock.patch.object(resume, "git_summary", return_value={"state": "unverified", "reason": "no_committed_git_baseline"}):
            return resume.discover(self.root, hashes)

    def manifest(self, entries, extra=None):
        value = {"files": entries, **(extra or {})}
        write(self.root, "release-output/manifest.json", json.dumps(value))

    def test_new_nested_native_app_with_framework_clue_never_builds_or_writes(self):
        write(self.root, "apps/puzzle/ios/Puzzle.xcodeproj/project.pbxproj")
        write(self.root, "apps/puzzle/package.json", json.dumps({"dependencies": {"react-native": "1.0"}, "scripts": {"build": "DO_NOT_EXECUTE_SECRET"}}))
        before = tree(self.root)
        report = self.status()
        self.assertEqual(before, tree(self.root))
        self.assertEqual(report["targets"][0]["path"], "apps/puzzle/ios/Puzzle.xcodeproj")
        self.assertFalse(report["targets"][0]["build_verified"])
        self.assertEqual(report["framework_clues"][0]["framework"], "react_native")
        self.assertNotIn("DO_NOT_EXECUTE_SECRET", json.dumps(report))
        self.assertIn("inspect_existing_build_commands_and_required_local_prerequisites", [x["action"] for x in report["next_actions"]])

    def test_mid_build_android_and_unity_have_local_artifacts_not_completed_uploads(self):
        write(self.root, "android/settings.gradle.kts")
        write(self.root, "android/app/src/main/AndroidManifest.xml", "<manifest/>")
        write(self.root, "game/ProjectSettings/ProjectVersion.txt", "m_EditorVersion: 6000.0.0f1")
        (self.root / "game/Assets").mkdir()
        write(self.root, "release-output/builds/android/game.aab", "build-bytes")
        self.manifest([{"path": "builds/android/game.aab", "kind": "aab", "sha256": digest("build-bytes"), "bytes": 11}])
        report = self.status(True)
        self.assertEqual({item["kind"] for item in report["targets"]}, {"gradle_project", "android_manifest", "unity_project"})
        self.assertEqual(report["manifests"][0]["entries"][0]["verification"], "hash_matches")
        self.assertFalse(report["remote_verified_now"])
        self.assertEqual(report["artifacts"][0]["verification"], "unverified")
        self.assertEqual(report["authorization"], "not_inferred")

    def test_uploaded_stage_preserves_memory_decisions_and_requires_readback(self):
        write(self.root, "deploy/APP.md", "Product facts; SECRET_OWNER_FACT")
        write(self.root, "deploy/STATE.md", "Uploaded draft; pricing blocked_owner; SECRET_REVIEW_PASSWORD")
        write(self.root, "release-output/apple-sections.md", "Recorded owner answer SECRET_LEGAL_DETAIL")
        write(self.root, "release-output/apple-upload-receipt.json", json.dumps({"status": "verified", "events": [{"status": "pending_external"}], "privateKey": "SECRET_KEY", "uploadOperations": [{"url": "SECRET_URL"}]}))
        before = tree(self.root)
        report = self.status()
        encoded = json.dumps(report)
        self.assertNotIn("SECRET_", encoded)
        self.assertEqual(before, tree(self.root))
        self.assertEqual(report["receipts"][0]["state"], "unverified")
        self.assertEqual(report["next_actions"][0]["action"], "read_existing_memory")
        self.assertIn("reconcile_cached_operation", [x["action"] for x in report["next_actions"]])
        self.assertTrue(any(x["role"] == "operation_or_section_journal" for x in report["documents"]))

    def test_changed_same_size_hash_missing_file_and_source_revision_staleness_are_distinct(self):
        write(self.root, "release-output/stores/ios/screen.png", "NEW!")
        self.manifest([{"path": "stores/ios/screen.png", "kind": "app_store_screenshot", "sha256": digest("OLD!"), "bytes": 4}, {"path": "builds/absent.ipa", "kind": "distribution-ipa", "sha256": "a" * 64}], {"source_revision": "a" * 40})
        with mock.patch.object(resume, "git_summary", return_value={"state": "present", "sha": "b" * 40, "tracked_changes": False}):
            report = resume.discover(self.root, True)
        manifest = report["manifests"][0]
        self.assertEqual(manifest["state"], "stale")
        self.assertEqual(manifest["entries"][0]["state"], "changed")
        self.assertEqual(manifest["entries"][0]["verification"], "hash_mismatch")
        self.assertEqual(manifest["entries"][1]["state"], "missing")
        self.assertIn("repair_only_affected_artifact_branch", [x["action"] for x in report["next_actions"]])
        self.assertEqual(self.status()["manifests"][0]["entries"][0]["verification"], "not_requested")

    def test_malformed_manifest_and_malformed_entry_are_reported_without_guessing(self):
        write(self.root, "release-output/manifest.json", "{not json")
        self.assertEqual(self.status()["manifests"][0]["reason"], "invalid_json")
        self.manifest([None, {"path": "missing", "kind": ["not a kind"]}])
        entries = self.status()["manifests"][0]["entries"]
        self.assertEqual(entries[0]["reason"], "invalid_entry")
        self.assertEqual(entries[1]["kind"], "other_local_artifact")
        write(self.root, "release-output/manifest.json", json.dumps({"files": "not-array"}))
        self.assertEqual(self.status()["manifests"][0]["reason"], "manifest_entries_required")

    def test_manifest_escape_symlink_and_private_keys_never_read_or_echo_rejected_paths(self):
        outside = write(self.root, "outside-secret.txt", "DO_NOT_READ_SECRET")
        (self.root / "release-output").mkdir()
        (self.root / "release-output/linked.png").symlink_to(outside)
        write(self.root, "release-output/AuthKey_SECRET.p8", "PRIVATE_KEY_BYTES")
        write(self.root, "release-output/credentials.json", "SECRET_CREDENTIALS")
        self.manifest([{"path": "../outside-secret.txt"}, {"path": str(outside)}, {"path": "linked.png"}, {"path": "AuthKey_SECRET.p8"}, {"path": "credentials.json"}, {"path": ".git/config"}])
        report = self.status(True)
        reasons = [entry["reason"] for entry in report["manifests"][0]["entries"]]
        self.assertEqual(reasons[:3], ["path_escape", "path_escape", "symlink_excluded"])
        self.assertEqual(reasons[3:], ["private_path_excluded"] * 3)
        encoded = json.dumps(report)
        self.assertNotIn("outside-secret", encoded)
        self.assertNotIn("PRIVATE_KEY_BYTES", encoded)
        self.assertNotIn("credentials.json", encoded)

    def test_scan_skips_dependencies_builds_symlinks_and_limits_depth(self):
        write(self.root, "node_modules/fake/Fake.xcodeproj/project.pbxproj")
        write(self.root, "build/fake/Fake.xcodeproj/project.pbxproj")
        write(self.root, "Pods/fake/settings.gradle")
        write(self.root, "real/App.xcodeproj/project.pbxproj")
        (self.root / "alias").symlink_to(self.root / "real", target_is_directory=True)
        write(self.root, "one/two/three/four/five/six/seven/Hidden.xcodeproj/project.pbxproj")
        report = self.status()
        self.assertEqual([x["path"] for x in report["targets"]], ["real/App.xcodeproj"])
        self.assertIn("project_depth_limit", report["limits"])
        with mock.patch.object(resume, "MAX_DIRECTORIES", 1):
            self.assertIn("project_scan_budget_exceeded", self.status()["limits"])

    def test_workspace_packages_can_contain_actual_apps_and_unity_dependencies_stay_skipped(self):
        write(self.root, "packages/mobile/ios/App.xcodeproj/project.pbxproj")
        write(self.root, "unity/ProjectSettings/ProjectVersion.txt")
        (self.root / "unity/Assets").mkdir()
        write(self.root, "unity/Packages/vendor/Hidden.xcodeproj/project.pbxproj")
        paths = [x["path"] for x in self.status()["targets"]]
        self.assertIn("packages/mobile/ios/App.xcodeproj", paths)
        self.assertNotIn("unity/Packages/vendor/Hidden.xcodeproj", paths)

    def test_hash_and_json_limits_are_explicit(self):
        write(self.root, "release-output/blob.bin", "123456789")
        self.manifest([{"path": "blob.bin", "sha256": digest("123456789")}])
        with mock.patch.object(resume, "MAX_HASH_FILE", 4):
            self.assertEqual(self.status(True)["manifests"][0]["entries"][0]["verification"], "hash_budget_exceeded")
        with mock.patch.object(resume, "MAX_JSON_BYTES", 2):
            self.assertEqual(self.status()["manifests"][0]["reason"], "json_size_limit")

    def test_artifacts_schema_and_directory_archive_do_not_claim_tree_verification(self):
        write(self.root, "release-output/builds/ios/App.xcarchive/Products/App.app/Info.plist")
        write(self.root, "release-output/manifest.json", json.dumps({"artifacts": [{"path": "builds/ios/App.xcarchive", "kind": "archive", "treeSHA256": "a" * 64}]}))
        report = self.status(True)
        self.assertEqual(report["manifests"][0]["entries"][0]["verification"], "directory_contents_unverified")
        self.assertEqual(len(report["artifacts"]), 1)

    def test_adopt_only_writes_discovery_and_detects_later_memory_change(self):
        state = write(self.root, "deploy/STATE.md", "owner decision retained")
        write(self.root, "deploy/APP.md", "known facts")
        write(self.root, ".shippykit/install.json", '{"existing":"installer"}')
        before = tree(self.root)
        report = self.status()
        resume.adopt(self.root, report)
        after = tree(self.root)
        self.assertEqual({key: after[key] for key in before}, before)
        self.assertEqual(set(after) - set(before), {".shippykit/discovery.json"})
        state.write_text("new valid owner decision", encoding="utf-8")
        updated = self.status()
        self.assertEqual(next(x for x in updated["documents"] if x["path"] == "deploy/STATE.md")["state"], "changed")
        self.assertNotIn("MEMORY.md", json.dumps(updated))

    def test_adopt_refuses_symlink_and_unowned_snapshot_without_overwrite(self):
        outside = self.root / "outside"
        outside.mkdir()
        (self.root / ".shippykit").symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "symlink"):
            resume.adopt(self.root, self.status())
        (self.root / ".shippykit").unlink()
        snapshot = write(self.root, ".shippykit/discovery.json", '{"valuable":"unknown-format"}')
        with self.assertRaisesRegex(ValueError, "unrecognized"):
            resume.adopt(self.root, self.status())
        self.assertEqual(snapshot.read_text(), '{"valuable":"unknown-format"}')

    def test_cli_status_no_side_effects_and_no_environment_secret_output(self):
        write(self.root, "App.xcodeproj/project.pbxproj")
        before = tree(self.root)
        output = io.StringIO()
        with mock.patch.dict(os.environ, {"ASC_PRIVATE_KEY": "NEVER_PRINT_SECRET"}), mock.patch.object(resume, "git_summary", return_value={"state": "unverified"}), contextlib.redirect_stdout(output):
            code = resume.main(["status", "--project", str(self.root), "--json"])
        self.assertEqual(code, 0)
        self.assertEqual(tree(self.root), before)
        self.assertNotIn("NEVER_PRINT_SECRET", output.getvalue())
        self.assertNotIn(str(self.root), output.getvalue())

    def test_legacy_handoff_and_appstore_work_evidence_are_indexed_without_private_contents(self):
        write(self.root, "CLAUDE.md", "SECRET_OLD_INSTRUCTIONS")
        write(self.root, "docs/AGENT_HANDOFF.md", "SECRET_OWNER_HISTORY")
        write(self.root, "docs/worklog.md", "SECRET_WORKLOG")
        write(self.root, "appstore/listing.md", "SECRET_LISTING_DRAFT")
        write(self.root, "appstore/work/asc-media-verified.json", '{"status":"verified","password":"SECRET_PASSWORD"}')
        write(self.root, "appstore/work/media-verified.json", '{"status":"verified"}')
        write(self.root, "release-output/apple-media-readback-20261024.json", '{"status":"verified"}')
        write(self.root, "release-output/google-console.json", '{"status":"verified"}')
        write(self.root, "release-output/google-listing-readback.json", '{"status":"verified"}')
        write(self.root, "release-output/android-upload-key.json", '{"private_key":"SECRET_KEY"}')
        report = self.status()
        paths = {item["path"] for item in report["documents"]}
        self.assertTrue({"CLAUDE.md", "docs/AGENT_HANDOFF.md", "docs/worklog.md", "appstore/listing.md"}.issubset(paths))
        self.assertEqual(len(report["receipts"]), 5)
        self.assertNotIn("SECRET_", json.dumps(report))
        self.assertNotIn("android-upload-key", json.dumps(report))
        self.assertIn("CLAUDE.md", report["next_actions"][0]["paths"])

    def test_derived_data_and_appledouble_are_excluded_and_windows_paths_rejected(self):
        write(self.root, "scratchpad/DerivedData-device/SourcePackages/checkouts/Dependency.xcodeproj/project.pbxproj")
        write(self.root, "DerivedData-sim/Dependency.xcodeproj/project.pbxproj")
        write(self.root, "SourcePackages/checkouts/Dependency.xcodeproj/project.pbxproj")
        write(self.root, "docs/._launch-prompt.md", "APPLEDOUBLE_BYTES")
        self.manifest([{"path": "C:outside.txt"}, {"path": "stores/image.png:stream"}])
        report = self.status(True)
        self.assertEqual(report["targets"], [])
        self.assertNotIn("._launch", json.dumps(report))
        self.assertTrue(all(item["reason"] == "invalid_relative_path" for item in report["manifests"][0]["entries"]))

    def test_cached_phone_record_does_not_recommend_store_reconciliation(self):
        write(self.root, "release-output/phone-status.json", '{"status":"verified"}')
        report = self.status()
        self.assertEqual(report["receipts"][0]["observation_scope"], "local_device_or_prerequisite")
        self.assertNotIn("reconcile_cached_operation", [item["action"] for item in report["next_actions"]])

    def test_exact_artwork_revision_journal_is_resume_memory_with_change_detection(self):
        journal = write(self.root, "release-output/artwork/revisions.json", '{"private_prompt":"SECRET_ARTWORK_PROMPT"}')
        write(self.root, "release-output/artwork/preview.png", "revision-preview")
        self.manifest([{"path": "artwork/preview.png", "kind": "asset_revision_preview", "sha256": digest("revision-preview")}])
        write(self.root, "other/revisions.json", '{"private":"SECRET_OTHER"}')
        write(self.root, "release-output/elsewhere/revisions.json", '{"private":"SECRET_ELSEWHERE"}')
        first = self.status(True)
        self.assertEqual(first["manifests"][0]["entries"][0]["kind"], "asset_revision_preview")
        self.assertEqual(first["manifests"][0]["entries"][0]["verification"], "hash_matches")
        docs = [item for item in first["documents"] if item["path"].endswith("revisions.json")]
        self.assertEqual(len(docs), 1)
        self.assertEqual(docs[0]["path"], "release-output/artwork/revisions.json")
        self.assertEqual(docs[0]["role"], "operation_or_section_journal")
        self.assertNotIn("SECRET_", json.dumps(first))
        self.assertIn(docs[0]["path"], first["next_actions"][0]["paths"])
        resume.adopt(self.root, first)
        journal.write_text('{"revision":2,"private_prompt":"SECRET_NEW"}', encoding="utf-8")
        second = self.status()
        self.assertEqual(next(item for item in second["documents"] if item["path"] == docs[0]["path"])["state"], "changed")

    def test_uploaded_media_index_is_memory_without_scanning_private_originals(self):
        index = write(self.root, "release-output/inputs/index.json", '{"original_filename":"PRIVATE_USER_FILENAME","role":"edit_target"}')
        write(self.root, "release-output/inputs/photo/PRIVATE_ORIGINAL.png", "original")
        write(self.root, "release-output/inputs/other/original.ipa", "not-a-release-build")
        write(self.root, "release-output/inputs/other/manifest.json", '{"files":[]}')
        write(self.root, "release-output/unrelated/index.json", '{"private":"PRIVATE_UNRELATED"}')
        first = self.status(True)
        documents = [row for row in first["documents"] if row["path"].endswith("index.json")]
        self.assertEqual(len(documents), 1)
        self.assertEqual(documents[0]["path"], "release-output/inputs/index.json")
        self.assertIn(documents[0]["path"], first["next_actions"][0]["paths"])
        self.assertEqual(first["artifacts"], [])
        self.assertEqual(first["manifests"], [])
        self.assertNotIn("PRIVATE_", json.dumps(first))
        resume.adopt(self.root, first)
        index.write_text('{"inputs":[],"private":"PRIVATE_NEW"}', encoding="utf-8")
        second = self.status()
        self.assertEqual(next(row for row in second["documents"] if row["path"] == documents[0]["path"])["state"], "changed")

    def test_real_git_summary_omits_remotes_and_detects_tracked_dirty_state(self):
        git = shutil_which_git()
        if not git:
            self.skipTest("git unavailable")
        def command(*args):
            subprocess.run([git, "-C", str(self.root), *args], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        command("init")
        write(self.root, "app.txt", "original")
        command("add", "app.txt")
        command("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-m", "fixture")
        command("remote", "add", "origin", "https://SECRET_PASSWORD@example.invalid/private.git")
        clean = resume.git_summary(self.root)
        self.assertFalse(clean["tracked_changes"])
        write(self.root, "app.txt", "changed")
        dirty = resume.git_summary(self.root)
        self.assertTrue(dirty["tracked_changes"])
        self.assertEqual(len(dirty["sha"]), 40)
        self.assertNotIn("SECRET", json.dumps(dirty))


def shutil_which_git():
    import shutil
    return shutil.which("git", path=os.defpath)


if __name__ == "__main__":
    unittest.main()
