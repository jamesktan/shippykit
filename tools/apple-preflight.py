#!/usr/bin/env python3
"""Read-only local Apple release checks. Never logs in, reads API keys, signs, or uploads.

Exit 0 means local checks passed; Apple account/store readiness remains unverified.
Exit 1 means a local blocker; exit 2 means invalid input. Only --output writes a report.
"""
import argparse
import datetime as dt
import json
import os
from pathlib import Path
import plistlib
import re
import subprocess
import sys
from urllib.parse import urlparse
import zipfile

FIELDS = {
    "app": {"project", "scheme", "bundle_id", "team_id", "version", "build_number"},
    "access": {"mode", "key_path_env", "key_id_env", "issuer_id_env"},
    "signing": {"style"},
    "release": {"goal", "mode", "not_before", "authorization_ref"},
    "listing": {"privacy_policy_url", "support_url"},
    "artifacts": {"archive", "ipa", "media_manifest"},
}
GOALS = {"upload_draft", "testflight_internal", "submit_for_review", "release"}


def validate(config):
    if not isinstance(config, dict) or config.get("schema_version") != 1:
        raise ValueError("Expected schema_version 1 object")
    if set(config) != set(FIELDS) | {"schema_version"}:
        raise ValueError("Unexpected or missing config sections; use apple-release.example.json")
    for section, allowed in FIELDS.items():
        values = config[section]
        if not isinstance(values, dict) or set(values) - allowed:
            raise ValueError(f"Invalid {section} fields; store secret references, never secret values")
        if any(v is not None and not isinstance(v, str) for v in values.values()):
            raise ValueError(f"{section} values must be strings or null")
    app = config["app"]
    for key in FIELDS["app"]:
        if not app.get(key):
            raise ValueError(f"Missing app.{key}")
    if not re.fullmatch(r"[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+", app["bundle_id"]):
        raise ValueError("Use an explicit reverse-domain bundle identifier")
    if not re.fullmatch(r"[A-Z0-9]{10}", app["team_id"]) or app["team_id"] == "REPLACE_ME":
        raise ValueError("Set the actual ten-character Apple team ID")
    access = config["access"]
    if access.get("mode") not in {"team_api_key", "individual_api_key", "xcode_account"}:
        raise ValueError("Invalid access.mode")
    for key, value in access.items():
        if key.endswith("_env") and value is not None and not re.fullmatch(r"[A-Z_][A-Z0-9_]*", value):
            raise ValueError(f"access.{key} must name an environment variable, not contain its value")
    if config["signing"].get("style") not in {"automatic", "manual"}:
        raise ValueError("Invalid signing.style")
    release = config["release"]
    if release.get("goal") not in GOALS or release.get("mode") not in {"manual", "automatic", "scheduled"}:
        raise ValueError("Invalid release goal or mode")
    if release["mode"] == "scheduled" and not release.get("not_before"):
        raise ValueError("Scheduled release requires not_before")
    if release.get("not_before"):
        scheduled = dt.datetime.fromisoformat(release["not_before"].replace("Z", "+00:00"))
        if scheduled.tzinfo is None:
            raise ValueError("not_before must include a timezone")
    return config


def run(argv, env, data=None):
    try:
        return subprocess.run(argv, input=data, capture_output=True, timeout=30, env=env)
    except (OSError, subprocess.TimeoutExpired):
        return None


def profile_facts(profile):
    if not isinstance(profile, dict) or not isinstance(profile.get("Entitlements", {}), dict):
        raise ValueError("Invalid provisioning profile metadata")
    entitlements = profile.get("Entitlements", {})
    kind = ("development" if entitlements.get("get-task-allow") else
            "enterprise" if profile.get("ProvisionsAllDevices") else
            "ad_hoc" if "ProvisionedDevices" in profile else "app_store")
    expiry = profile.get("ExpirationDate")
    if isinstance(expiry, dt.datetime) and expiry.tzinfo is None:
        expiry = expiry.replace(tzinfo=dt.timezone.utc)
    return {"kind": kind, "team_ids": profile.get("TeamIdentifier", []),
            "application_identifier": entitlements.get("application-identifier"),
            "expired": expiry <= dt.datetime.now(dt.timezone.utc) if isinstance(expiry, dt.datetime) else None}


def inspect_ipa(path):
    with zipfile.ZipFile(path) as archive:
        if archive.testzip() is not None:
            raise ValueError("IPA ZIP integrity failed")
        names = [n for n in archive.namelist() if re.fullmatch(r"Payload/[^/]+\.app/Info.plist", n)]
        if len(names) != 1:
            raise ValueError("IPA must contain exactly one root app Info.plist")
        prefix = names[0].rsplit("/", 1)[0]
        info = plistlib.loads(archive.read(names[0]))
        if not isinstance(info, dict):
            raise ValueError("App Info.plist must be a dictionary")
        profile = archive.read(prefix + "/embedded.mobileprovision") if prefix + "/embedded.mobileprovision" in archive.namelist() else None
        extensions = any(".appex/Info.plist" in n for n in archive.namelist())
        return info, profile, extensions


def assess(config, project, env=None):
    validate(config)
    env = dict(os.environ if env is None else env)
    project = Path(project).resolve()
    # --project may be an app subdirectory; a worktree's .git is a file.
    source_roots = [project] + [p for p in (project, *project.parents) if (p / ".git").exists()]
    checks = []
    def check(name, status, detail, stage="upload", actor="agent"):
        checks.append(dict(id=name, status=status, detail=detail, stage=stage, next_actor=actor))
    def path_for(value):
        p = Path(value).expanduser()
        return p if p.is_absolute() else project / p
    app, access = config["app"], config["access"]
    project_path = path_for(app["project"])
    valid_project = project_path.is_dir() and project_path.suffix in {".xcodeproj", ".xcworkspace"}
    check("project", "pass" if valid_project else "fail", "Xcode project/workspace must exist")
    check("scheme", "unknown", "Verify the configured scheme and Release targets with xcodebuild -list")
    developer = env.get("DEVELOPER_DIR")
    if not developer and Path("/Applications/Xcode.app/Contents/Developer").is_dir():
        env["DEVELOPER_DIR"] = "/Applications/Xcode.app/Contents/Developer"
    result = run(["xcodebuild", "-version"], env)
    version = result.stdout.decode(errors="replace").strip() if result and result.returncode == 0 else ""
    check("xcode", "pass" if version.startswith("Xcode ") else "fail",
          version if version.startswith("Xcode ") else "Select an installed full Xcode via DEVELOPER_DIR")
    check("current_sdk_policy", "unknown", "Verify Apple's current submission SDK requirements against this build")
    mode = access["mode"]
    if mode == "xcode_account":
        check("account_session", "unknown", "Xcode account login and portal access require a live check", actor="owner")
    else:
        fields = ["key_path_env", "key_id_env"] + (["issuer_id_env"] if mode == "team_api_key" else [])
        for key in fields:
            name = access.get(key)
            value = env.get(name, "") if name else ""
            present = bool(value)
            if key == "key_path_env" and present:
                secret_path = Path(value).expanduser()
                present = secret_path.is_file()
                if present and any(secret_path.resolve().is_relative_to(root) for root in source_roots):
                    check("key_storage", "fail", "Move the private key outside the source repository", actor="owner")
            check(key, "pass" if present else "fail", f"{name or key}: reference {'available' if present else 'missing'}; key contents were not read", actor="owner")
        if mode == "individual_api_key" and config["signing"]["style"] == "automatic":
            check("provisioning_access", "unknown", "Individual keys cannot provision; supply an independent Xcode/team-key signing route or existing manual signing assets", actor="owner")
        check("api_access", "unknown", "Key presence does not verify Apple authentication, team, role, or app access", actor="owner")
    for field in ("privacy_policy_url", "support_url"):
        value = config["listing"].get(field)
        valid = bool(value and urlparse(value).scheme == "https" and urlparse(value).hostname)
        check(field, "unknown" if valid else "fail", "Verify public URL content and reachability" if valid else "Supply the actual public HTTPS URL", "review", "owner")
    media = config["artifacts"].get("media_manifest")
    check("media_manifest", "pass" if media and path_for(media).is_file() else "fail",
          "A media manifest is required before review; separately verify its hashes, dimensions and claims", "review")
    archive_value = config["artifacts"].get("archive")
    if archive_value:
        archive = path_for(archive_value)
        apps = [p for p in (archive / "Products/Applications").glob("*.app")
                if p.is_dir() and not p.name.startswith("._")]
        check("archive", "pass" if len(apps) == 1 else "fail", "Expected one app in the Release archive")
    ipa_value = config["artifacts"].get("ipa")
    ipa = path_for(ipa_value) if ipa_value else None
    if ipa is None or not ipa.is_file():
        check("distribution_ipa", "fail", "Export an App Store distribution IPA; an archive alone is not an upload")
    else:
        try:
            info, profile_data, extensions = inspect_ipa(ipa)
            expected = {"CFBundleIdentifier": app["bundle_id"], "CFBundleShortVersionString": app["version"], "CFBundleVersion": app["build_number"]}
            for key, value in expected.items():
                check(key, "pass" if info.get(key) == value else "fail", f"IPA {key} {'matches' if info.get(key) == value else 'does not match'} configured release")
            check("device_platform", "pass" if info.get("CFBundleSupportedPlatforms") == ["iPhoneOS"] else "fail", "App Store needs a device build, not a simulator build")
            decoded = run(["security", "cms", "-D"], env, profile_data) if profile_data else None
            if decoded and decoded.returncode == 0:
                facts = profile_facts(plistlib.loads(decoded.stdout))
                check("distribution_profile", "pass" if facts["kind"] == "app_store" else "fail", f"Root IPA profile type: {facts['kind']}; development/ad-hoc/enterprise exports do not establish App Store readiness")
                check("profile_team", "pass" if app["team_id"] in facts["team_ids"] else "fail", "Profile team must match the configured personal/organization team")
                identifier = facts["application_identifier"] or ""
                check("profile_bundle", "pass" if identifier.partition(".")[2] == app["bundle_id"] else "fail", "Distribution profile must name the exact bundle ID")
                check("profile_expiry", "unknown" if facts["expired"] is None else "fail" if facts["expired"] else "pass", "Root IPA profile expiry checked")
            else:
                check("distribution_profile", "unknown", "Could not inspect the root provisioning profile; verify distribution export independently")
            check("signature_entitlements", "unknown", "Verify signatures, entitlements, nested bundles and distribution export with Xcode; profile inspection alone is insufficient")
            if extensions:
                check("extension_signing", "unknown", "Verify each extension's separate bundle ID, entitlements and distribution profile")
        except (OSError, ValueError, zipfile.BadZipFile, plistlib.InvalidFileException):
            check("distribution_ipa", "fail", "IPA or provisioning metadata could not be decoded")
    for name, detail, stage in [
        ("membership_agreements", "Verify active membership and current agreements", "upload"),
        ("app_record", "Verify/reuse the exact app record, bundle ID, team, capabilities and next build number", "upload"),
        ("listing_declarations", "Verify metadata/media, privacy, age rating, export compliance, review access, price and territories", "review"),
        ("review_and_availability", "Apple processing, review approval and storefront availability are separate observed states", "release"),
    ]:
        check(name, "unknown", detail, stage, "owner" if name == "membership_agreements" else "agent")
    check("release_authorization", "unknown", "A config goal or authorization reference is not proof of user authorization; use the actual session/policy", "review", "owner")
    if config["release"]["goal"] in {"submit_for_review", "release"} and config["release"]["mode"] in {"automatic", "scheduled"}:
        check("public_release_authorization", "unknown", "Review submission with automatic/scheduled release can publish after approval; verify authorization for public release", "review", "owner")
    stages = {"upload"}
    if config["release"]["goal"] in {"submit_for_review", "release"}:
        stages.add("review")
    if config["release"]["goal"] == "release":
        stages.add("release")
    blockers = [c["id"] for c in checks if c["status"] == "fail" and c["stage"] in stages]
    return {"schema_version": 1, "checked_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "bundle_id": app["bundle_id"], "team_id": app["team_id"], "goal": config["release"]["goal"],
            "local_status": "blocked" if blockers else "passed", "store_readiness": "unverified",
            "account_or_store_writes_performed": False, "blocking_local_checks": blockers, "checks": checks}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, default=Path.cwd())
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        report = assess(json.loads(args.config.read_text()), args.project)
        text = json.dumps(report, indent=2) + "\n"
        if args.output:
            if args.output.resolve() == args.config.resolve():
                raise ValueError("Output must not overwrite the input configuration")
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(text)
        print(text, end="")
        return 1 if report["blocking_local_checks"] else 0
    except (ValueError, OSError, KeyError, TypeError):
        # Do not echo configuration values: a mistaken input could contain a secret.
        print("Invalid input or inaccessible file. Use the documented configuration fields and actual project paths; no secret values are accepted.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
