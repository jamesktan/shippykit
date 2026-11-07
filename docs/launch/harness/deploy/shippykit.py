#!/usr/bin/env python3
"""Bounded local discovery for ShippyKit. Python 3.9+, standard library only.

`status` never writes or contacts a store. `adopt` writes a disposable discovery
snapshot; APP.md, STATE.md and existing journals remain the durable memory.
`updates` explicitly checks the official package version without changing files.
"""
import argparse
import datetime
import hashlib
import http.client
import json
import os
from pathlib import Path
import queue
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request

MAX_DEPTH = 5
MAX_DIRECTORIES = 240
MAX_ENTRIES = 5000
MAX_RELEASE_ENTRIES = 1200
MAX_MANIFEST_ITEMS = 500
MAX_JSON_BYTES = 2 * 1024 * 1024
MAX_HASH_FILE = 32 * 1024 * 1024
MAX_HASH_TOTAL = 128 * 1024 * 1024
SKIP_DIRECTORIES = {
    ".git", "node_modules", "pods", "carthage", "vendor", ".venv", "venv",
    "__pycache__", ".gradle", ".dart_tool", ".next", ".nuxt", "build", "builds",
    "dist", "target", "deriveddata", "library", "temp", "obj", "logs", "cache",
    "caches", ".cache", "bower_components", "coverage", ".shippykit", "scratchpad", "sourcepackages", "checkouts",
}
PRIVATE_SUFFIXES = {".p8", ".p12", ".pfx", ".pem", ".key", ".keystore", ".jks", ".mobileprovision", ".provisionprofile"}
PRIVATE_NAMES = {".env", "credentials", "secrets", "private", "profiles", "certificates", "keychains", "auth", "cookies"}
MEMORY_NAMES = {"APP.md", "STATE.md"}
LEGACY_MEMORY_NAMES = {"CLAUDE.md", "AGENT_HANDOFF.md", "HANDOFF.md", "WORKLOG.md", "WORK_LOG.md"}
JOURNAL_NAMES = {"apple-sections.md", "google-sections.md", "operation-journal.md", "release-journal.md"}
ARTIFACT_SUFFIXES = {".ipa": "ios_distribution_candidate", ".apk": "android_install_candidate", ".aab": "android_store_candidate", ".xcarchive": "apple_archive", ".app": "apple_app_bundle"}
PUBLIC_KINDS = {"app_store_screenshot", "store-screenshot", "app_store_preview", "preview_poster", "promo_image", "promo_video", "store_copy", "listing", "preview_copy", "app_icon", "store_icon", "launcher_icon", "asset_revision_preview", "distribution-ipa", "archive", "apk", "aab", "raw_screenshot", "raw_video", "native-screenshot"}
CHECKPOINT_STATES = {"not_started", "in_progress", "verified", "blocked_owner", "pending_external", "failed", "not_applicable", "upload_intent", "transport_returned", "observed"}
SHA_RE = re.compile(r"^[a-fA-F0-9]{7,64}$")
UPDATE_URL = "https://raw.githubusercontent.com/jamesktan/shippykit/main/docs/launch/harness/VERSION"
UPDATE_API_PATH = "repos/jamesktan/shippykit/contents/docs/launch/harness/VERSION?ref=main"
UPDATE_API_URL = "https://api.github.com/" + UPDATE_API_PATH
UPDATE_TIMEOUT_SECONDS = 5
MAX_VERSION_BYTES = 256
SEMVER_RE = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?(?:\+([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?$")


def parse_semver(value):
    """SemVer 2.0 precedence; build metadata never affects ordering."""
    if not isinstance(value, str) or len(value) > 128:
        raise ValueError("invalid_semver")
    match = SEMVER_RE.fullmatch(value)
    if not match:
        raise ValueError("invalid_semver")
    prerelease = match.group(4).split(".") if match.group(4) else []
    if any(part.isdigit() and len(part) > 1 and part.startswith("0") for part in prerelease):
        raise ValueError("invalid_semver")
    return tuple(int(match.group(index)) for index in (1, 2, 3)), prerelease


def compare_semver(left, right):
    left_core, left_pre = parse_semver(left)
    right_core, right_pre = parse_semver(right)
    if left_core != right_core:
        return 1 if left_core > right_core else -1
    if not left_pre or not right_pre:
        return (bool(right_pre) - bool(left_pre))
    for first, second in zip(left_pre, right_pre):
        if first == second:
            continue
        if first.isdigit() and second.isdigit():
            return 1 if int(first) > int(second) else -1
        if first.isdigit() != second.isdigit():
            return -1 if first.isdigit() else 1
        return 1 if first > second else -1
    return (len(left_pre) > len(right_pre)) - (len(left_pre) < len(right_pre))


class NoUpdateRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, new_url):
        return None


def github_cli_version():
    """Read the fixed VERSION with existing gh access, bounded bytes and lifetime."""
    gh = shutil.which("gh")
    if not gh:
        return None, "github_cli_unavailable"
    environment = os.environ.copy()
    for key in ("GH_DEBUG", "DEBUG", "GH_FORCE_TTY", "GH_HTTP_UNIX_SOCKET", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY", "http_proxy", "https_proxy", "all_proxy", "no_proxy"):
        environment.pop(key, None)
    environment.update(GH_HOST="github.com", GH_PROMPT_DISABLED="1", GIT_TERMINAL_PROMPT="0", GH_NO_UPDATE_NOTIFIER="1", GH_NO_EXTENSION_UPDATE_NOTIFIER="1", GH_PAGER="cat", PAGER="cat")
    command = [gh, "api", "--hostname", "github.com", "--method", "GET", UPDATE_API_PATH, "--header", "Accept:application/vnd.github.raw+json"]
    try:
        process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, shell=False, env=environment, cwd=os.path.abspath(os.sep))
    except OSError:
        return None, "github_cli_unavailable"
    # Pipe reads are not selectable on Windows. A bounded reader works on all
    # supported hosts; it never accumulates more than the VERSION cap + 1 byte.
    output = queue.Queue(maxsize=1)

    def read_output():
        try:
            output.put((process.stdout.read(MAX_VERSION_BYTES + 1), None))
        except (OSError, ValueError):
            output.put((None, "github_cli_unavailable"))
        finally:
            try:
                process.stdout.close()
            except OSError:
                pass

    reader = threading.Thread(target=read_output, daemon=True)
    deadline = time.monotonic() + UPDATE_TIMEOUT_SECONDS
    reader.start()
    try:
        raw, error = output.get(timeout=max(0, deadline - time.monotonic()))
        if error:
            return None, error
        if len(raw) > MAX_VERSION_BYTES:
            return None, "version_response_too_large"
        if process.wait(timeout=max(0, deadline - time.monotonic())) != 0:
            return None, "github_cli_access_unavailable"
        return raw, None
    except (queue.Empty, subprocess.TimeoutExpired):
        return None, "github_cli_timeout"
    except OSError:
        return None, "github_cli_unavailable"
    finally:
        if process.poll() is None:
            try:
                process.kill()
            except OSError:
                pass
            try:
                process.wait(timeout=1)
            except (OSError, subprocess.TimeoutExpired):
                pass
        reader.join(timeout=1)


def check_updates(project, opener=None):
    """Explicit official VERSION read; never install, log in or write a cache."""
    result = {
        "schema_version": 1, "mode": "update_check", "status": "unavailable",
        "installed_version": None, "latest_version": None,
        "source_url": UPDATE_URL, "transport": "anonymous_https", "automatic_update": False,
        "checked_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    try:
        root = Path(project).expanduser().resolve(strict=True)
        if not root.is_dir():
            raise ValueError("invalid_project")
        receipt = small_json(confined_file(root, ".shippykit/install.json"))
        if receipt.get("schema_version") != 1:
            raise ValueError("invalid_receipt_schema")
        installed = receipt.get("package_version")
        parse_semver(installed)
        result["installed_version"] = installed
        result["installed_version_basis"] = "installer_receipt"
        conflicts = receipt.get("conflicts", [])
        result["unresolved_conflicts"] = len(conflicts) if isinstance(conflicts, list) else None
    except (ValueError, OSError):
        result["reason"] = "installation_receipt_missing_or_invalid"
        return result
    if opener is None:
        # Do not inherit proxy credentials, install authentication handlers, follow
        # redirects or send any app/project identifiers with this public request.
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoUpdateRedirect())
    request = urllib.request.Request(UPDATE_URL, headers={"Accept": "text/plain", "User-Agent": "ShippyKit-update-check"}, method="GET")
    try:
        with opener.open(request, timeout=UPDATE_TIMEOUT_SECONDS) as response:
            if response.geturl() != UPDATE_URL:
                result["reason"] = "unexpected_update_response"
                return result
            if response.getcode() in (401, 403, 404):
                raise urllib.error.HTTPError(UPDATE_URL, response.getcode(), "access_unavailable", {}, None)
            if response.getcode() != 200:
                result["reason"] = "unexpected_update_response"
                return result
            raw = response.read(MAX_VERSION_BYTES + 1)
    except urllib.error.HTTPError as error:
        if error.fp is not None:
            error.close()
        if error.code not in (401, 403, 404) or error.filename != UPDATE_URL:
            result["reason"] = "update_source_unavailable"
            return result
        result.update(transport="existing_github_cli", source_url=UPDATE_API_URL)
        raw, reason = github_cli_version()
        if reason:
            result["reason"] = reason
            return result
    except (urllib.error.URLError, OSError, TimeoutError, http.client.HTTPException):
        result["reason"] = "update_source_unavailable"
        return result
    if len(raw) > MAX_VERSION_BYTES:
        result["reason"] = "version_response_too_large"
        return result
    try:
        latest = raw.decode("ascii").rstrip("\r\n")
        parse_semver(latest)
    except (UnicodeError, ValueError):
        result["reason"] = "invalid_latest_version"
        return result
    result["latest_version"] = latest
    comparison = compare_semver(latest, installed)
    result["status"] = "update_available" if comparison > 0 else "installed_ahead" if comparison < 0 else "up_to_date"
    return result


def updates_text(report):
    status = report["status"]
    if status == "update_available":
        message = "ShippyKit {} is available (installed {}). Continue your current task; updating requires an update instruction. See deploy/START.md.".format(report["latest_version"], report["installed_version"])
    elif status == "up_to_date":
        message = "ShippyKit {}: no newer published version found.".format(report["installed_version"])
    elif status == "installed_ahead":
        message = "Installed ShippyKit {} is newer than published {}; no downgrade suggested.".format(report["installed_version"], report["latest_version"])
    else:
        message = "ShippyKit update check unavailable ({}). Installed files remain usable; continue the requested task.".format(report.get("reason", "unknown"))
    if report.get("transport") == "existing_github_cli":
        message += " Version source: existing GitHub CLI access; no login or installation was attempted."
    if report.get("unresolved_conflicts"):
        message += " The installation receipt lists {} unresolved customized-file conflicts; inspect them before relying on the new capability.".format(report["unresolved_conflicts"])
    return message


def safe_name(name):
    lower = name.lower()
    return not ((name.startswith(".") and name != ".shippykit") or lower in PRIVATE_NAMES or lower.startswith(".env") or Path(name).suffix.lower() in PRIVATE_SUFFIXES or re.search(r"(^|[-_.])(secrets?|passwords?|credentials?|tokens?|private[-_]key|upload[-_]key|signing[-_]key|service[-_]account)([-_.]|$)", lower))


def relative(root, filename):
    return filename.relative_to(root).as_posix()


def confined_file(root, raw):
    """Manifest references are relative, local and never follow a symlink."""
    if not isinstance(raw, str) or not raw or "\\" in raw or "\x00" in raw or ":" in raw:
        raise ValueError("invalid_relative_path")
    parts = raw.split("/")
    if Path(raw).is_absolute() or any(part in ("", ".", "..") for part in parts):
        raise ValueError("path_escape")
    cursor = root
    for part in parts:
        if not safe_name(part):
            raise ValueError("private_path_excluded")
        cursor = cursor / part
        if cursor.is_symlink():
            raise ValueError("symlink_excluded")
    return cursor


def small_json(filename):
    if filename.is_symlink() or not filename.is_file():
        raise ValueError("not_regular_file")
    if filename.stat().st_size > MAX_JSON_BYTES:
        raise ValueError("json_size_limit")
    try:
        result = json.loads(filename.read_text(encoding="utf-8"))
    except (ValueError, UnicodeError, OSError) as error:
        raise ValueError("invalid_json") from error
    if not isinstance(result, dict):
        raise ValueError("json_object_required")
    return result


def fingerprint(filename, budget, enabled):
    if not enabled:
        return None, "not_requested"
    size = filename.stat().st_size
    if size > MAX_HASH_FILE or size > budget[0]:
        return None, "hash_budget_exceeded"
    digest = hashlib.sha256()
    consumed = 0
    with filename.open("rb") as stream:
        while True:
            chunk = stream.read(min(1024 * 1024, MAX_HASH_FILE - consumed + 1))
            if not chunk:
                break
            consumed += len(chunk)
            if consumed > MAX_HASH_FILE or consumed > budget[0]:
                return None, "hash_budget_exceeded"
            digest.update(chunk)
    budget[0] -= consumed
    return digest.hexdigest(), "checked"


def git_summary(root):
    """No remotes, user configuration, hooks, credential helpers or path lists."""
    git = shutil.which("git", path=os.defpath)
    if not git:
        return {"state": "unverified", "reason": "git_unavailable"}
    prefix = [git, "--no-optional-locks", "-c", "core.fsmonitor=false", "-c", "core.hooksPath=/dev/null", "-C", str(root)]
    env = {"PATH": os.defpath, "LC_ALL": "C", "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull, "GIT_OPTIONAL_LOCKS": "0"}
    try:
        head = subprocess.run(prefix + ["rev-parse", "--verify", "HEAD"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=5, env=env)
        value = head.stdout.decode("ascii", errors="ignore").strip()
        if head.returncode or not SHA_RE.fullmatch(value):
            return {"state": "unverified", "reason": "no_committed_git_baseline"}
        dirty = subprocess.run(prefix + ["diff", "--quiet", "--no-ext-diff", "--no-textconv", "HEAD", "--"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5, env=env)
        return {"state": "present", "sha": value, "tracked_changes": dirty.returncode == 1 if dirty.returncode in (0, 1) else None, "untracked_changes": "not_assessed", "scope": "repository_containing_selected_project", "remote_accessed": False}
    except (OSError, subprocess.TimeoutExpired):
        return {"state": "unverified", "reason": "git_observation_unavailable"}


def document_record(root, filename, role, budget):
    item = {"path": relative(root, filename), "role": role, "state": "present", "content": "not_reported"}
    try:
        item["sha256"], item["fingerprint"] = fingerprint(filename, budget, True)
    except OSError:
        item.update(state="unverified", reason="unreadable_file")
    return item


def scan_project(root, budget):
    targets, clues, documents, releases, receipts, limits = [], [], [], [], [], []
    pending = [(root, 0)]
    directories = entries = 0
    while pending:
        folder, depth = pending.pop(0)
        if directories >= MAX_DIRECTORIES or entries >= MAX_ENTRIES:
            limits.append("project_scan_budget_exceeded")
            break
        directories += 1
        try:
            with os.scandir(folder) as listing:
                children = []
                for child in listing:
                    entries += 1
                    if entries > MAX_ENTRIES:
                        limits.append("project_entry_budget_exceeded")
                        break
                    if child.is_symlink() or not safe_name(child.name):
                        continue
                    children.append(child)
        except OSError:
            limits.append("unreadable_directory")
            continue
        children.sort(key=lambda child: child.name)
        names = {child.name for child in children}
        unity = "Assets" in names and "ProjectSettings" in names
        if unity:
            marker = folder / "ProjectSettings" / "ProjectVersion.txt"
            if marker.is_file() and not marker.is_symlink():
                targets.append({"kind": "unity_project", "path": relative(root, folder), "state": "present", "platforms": "unverified", "build_verified": False})
        if "settings.gradle" in names or "settings.gradle.kts" in names:
            targets.append({"kind": "gradle_project", "path": relative(root, folder), "state": "present", "android_target": "unverified", "build_verified": False})
        if "AndroidManifest.xml" in names:
            targets.append({"kind": "android_manifest", "path": relative(root, folder / "AndroidManifest.xml"), "state": "present", "build_verified": False})
        for child in children:
            filename = Path(child.path)
            if child.is_dir(follow_symlinks=False):
                suffix = filename.suffix.lower()
                if suffix in (".xcodeproj", ".xcworkspace"):
                    targets.append({"kind": "xcode_project" if suffix == ".xcodeproj" else "xcode_workspace", "path": relative(root, filename), "state": "present", "ios_target": "unverified", "build_verified": False})
                    continue
                if child.name == "release-output":
                    releases.append(filename)
                    continue
                if child.name.lower() in SKIP_DIRECTORIES or child.name.lower().startswith("deriveddata") or child.name.startswith(".") or (unity and child.name in ("Assets", "Packages")):
                    continue
                if depth < MAX_DEPTH:
                    pending.append((filename, depth + 1))
                else:
                    limits.append("project_depth_limit")
                continue
            if not child.is_file(follow_symlinks=False):
                continue
            if child.name in MEMORY_NAMES:
                documents.append(document_record(root, filename, "app_facts" if child.name == "APP.md" else "checkpoints_and_decisions", budget))
            elif child.name in LEGACY_MEMORY_NAMES or re.search(r"handoff|work[-_ ]?log", child.name, re.I) and filename.suffix.lower() == ".md":
                documents.append(document_record(root, filename, "existing_project_memory", budget))
            elif child.name in JOURNAL_NAMES:
                documents.append(document_record(root, filename, "operation_or_section_journal", budget))
            elif filename.suffix.lower() == ".md" and (child.name in ("README.md", "AGENTS.md", "needs-input.md") or re.search(r"release|deployment|app.?store|play.?store|status|launch|listing", child.name, re.I)):
                documents.append({"path": relative(root, filename), "role": "existing_project_document", "state": "present", "content": "not_read"})
            if filename.suffix.lower() == ".json" and re.search(r"(?:^|/)(?:appstore|app-store|playstore|google-play)/(?:work|evidence)/", relative(root, filename), re.I) and re.search(r"verified|receipt|status|preflight|upload|delivery|readback|store-metadata|store-media|console", child.name, re.I):
                receipts.append(receipt_record(root, filename))
            if child.name == "package.json":
                try:
                    package = small_json(filename)
                    dependencies = set()
                    for key in ("dependencies", "devDependencies", "peerDependencies"):
                        if isinstance(package.get(key), dict):
                            dependencies.update(package[key])
                    for dependency, framework in (("react-native", "react_native"), ("expo", "expo"), ("@capacitor/core", "capacitor")):
                        if dependency in dependencies:
                            clues.append({"framework": framework, "path": relative(root, filename), "state": "unverified", "basis": "declared_dependency"})
                except ValueError:
                    pass
            elif child.name == "pubspec.yaml":
                # File existence is a Dart/Flutter clue, never proof of a working target.
                clues.append({"framework": "dart_or_flutter", "path": relative(root, filename), "state": "unverified", "basis": "manifest_filename"})
    return targets, clues, documents, releases, receipts, sorted(set(limits)), {"directories": directories, "entries": entries}


def manifest_inventory(root, release, filename, source, hash_budget, verify):
    result = {"path": relative(root, filename), "state": "present", "entries": [], "limits": []}
    try:
        manifest = small_json(filename)
        entries = manifest.get("files", manifest.get("artifacts"))
        if not isinstance(entries, list):
            raise ValueError("manifest_entries_required")
    except (ValueError, OSError) as error:
        result.update(state="unverified", reason=str(error) if isinstance(error, ValueError) else "unreadable_manifest")
        return result
    revision = manifest.get("source_revision") or manifest.get("app_source_revision")
    if not revision and isinstance(manifest.get("source"), dict):
        revision = manifest["source"].get("sourceRevision")
    if isinstance(revision, str) and SHA_RE.fullmatch(revision):
        result["recorded_source_revision"] = revision
        head = source.get("sha")
        if head and not (head.startswith(revision) or revision.startswith(head)):
            result.update(state="stale", reason="recorded_source_revision_differs")
    if len(entries) > MAX_MANIFEST_ITEMS:
        result["limits"].append("manifest_item_budget_exceeded")
    for index, entry in enumerate(entries[:MAX_MANIFEST_ITEMS]):
        if not isinstance(entry, dict):
            result["entries"].append({"index": index, "state": "unverified", "reason": "invalid_entry"})
            continue
        item = {"index": index, "kind": entry.get("kind") if isinstance(entry.get("kind"), str) and entry["kind"] in PUBLIC_KINDS else "other_local_artifact"}
        raw = entry.get("path")
        try:
            artifact = confined_file(release, raw)
            item["path"] = relative(root, artifact)
            if not artifact.exists():
                item.update(state="missing")
            elif artifact.is_dir():
                item.update(state="present", verification="directory_contents_unverified")
            elif not artifact.is_file():
                item.update(state="unverified", reason="not_regular_file")
            else:
                item.update(state="present", bytes=artifact.stat().st_size, verification="hash_unverified")
                if isinstance(entry.get("bytes"), int) and item["bytes"] != entry["bytes"]:
                    item.update(state="changed", reason="byte_count_mismatch")
                expected = entry.get("sha256")
                if isinstance(expected, str) and re.fullmatch(r"[a-fA-F0-9]{64}", expected):
                    item["expected_sha256"] = expected.lower()
                    digest, disposition = fingerprint(artifact, hash_budget, verify)
                    if digest:
                        item["sha256"] = digest
                        item["verification"] = "hash_matches" if digest == expected.lower() else "hash_mismatch"
                        if digest != expected.lower():
                            item.update(state="changed", reason="hash_mismatch")
                    else:
                        item["verification"] = disposition
                else:
                    item["verification"] = "no_valid_sha256"
        except (ValueError, OSError) as error:
            # Do not echo rejected paths; they may point at a key or outside this project.
            item.update(state="unverified", reason=str(error) if isinstance(error, ValueError) else "unreadable_artifact")
        result["entries"].append(item)
    return result


def receipt_record(root, filename):
    item = {"path": relative(root, filename), "state": "unverified", "basis": "cached_local_record", "remote_verified_now": False, "next_action": "reconcile_remote_if_store_scope_is_authorized"}
    if re.search(r"phone|device|preflight|capture", filename.name, re.I):
        item.update(observation_scope="local_device_or_prerequisite", next_action="recheck_local_dependency_if_relevant")
    else:
        item["observation_scope"] = "store_operation"
    try:
        doc = small_json(filename)
        events = doc.get("events", [])
        states = [doc.get("status"), doc.get("state")]
        if isinstance(doc.get("build"), dict):
            states.append(doc["build"].get("state"))
        if isinstance(events, list):
            for event in events[-30:]:
                if isinstance(event, dict):
                    states.extend([event.get("status"), event.get("event")])
        item["recorded_states"] = sorted({state for state in states if isinstance(state, str) and state in CHECKPOINT_STATES})
        item["uncertain_operation"] = any(state in ("pending_external", "upload_intent") for state in item["recorded_states"])
    except (ValueError, OSError):
        item["reason"] = "unreadable_or_malformed_cached_record"
    return item


def release_inventory(root, release, source, hash_budget, verify):
    manifests, receipts, artifacts, documents, limits = [], [], [], [], []
    pending = [(release, 0)]
    count = 0
    while pending and count < MAX_RELEASE_ENTRIES:
        folder, depth = pending.pop(0)
        try:
            with os.scandir(folder) as children:
                for child in children:
                    count += 1
                    if count > MAX_RELEASE_ENTRIES:
                        limits.append("release_entry_budget_exceeded")
                        break
                    if child.is_symlink() or not safe_name(child.name) or child.name.startswith("."):
                        continue
                    filename = Path(child.path)
                    if filename.suffix.lower() in ARTIFACT_SUFFIXES:
                        artifacts.append({"path": relative(root, filename), "kind": ARTIFACT_SUFFIXES[filename.suffix.lower()], "state": "present", "verification": "unverified"})
                        if child.is_dir(follow_symlinks=False):
                            continue
                    if child.is_dir(follow_symlinks=False):
                        if filename == release / "inputs":
                            index = filename / "index.json"
                            if index.is_file() and not index.is_symlink():
                                documents.append(document_record(root, index, "operation_or_section_journal", hash_budget))
                            # Imported originals are private inputs, not build receipts
                            # or app artifacts. Resume through the index, not filenames.
                            continue
                        if child.name.lower() in {"logs", "site", "profiles", "private", "cache", "node_modules"}:
                            continue
                        if depth < 4:
                            pending.append((filename, depth + 1))
                        else:
                            limits.append("release_depth_limit")
                    elif child.is_file(follow_symlinks=False):
                        if child.name == "manifest.json":
                            manifests.append(manifest_inventory(root, filename.parent, filename, source, hash_budget, verify))
                        elif child.name in JOURNAL_NAMES or filename.relative_to(release).as_posix() == "artwork/revisions.json":
                            documents.append(document_record(root, filename, "operation_or_section_journal", hash_budget))
                        elif filename.suffix.lower() == ".json" and re.search(r"receipt|status|preflight|upload|delivery|verified|readback|store-metadata|store-media|console", child.name, re.I):
                            receipts.append(receipt_record(root, filename))
                        elif child.name in ("README.md", "needs-input.md"):
                            documents.append({"path": relative(root, filename), "role": "existing_release_document", "state": "present", "content": "not_read"})
        except OSError:
            limits.append("unreadable_release_directory")
    return manifests, receipts, artifacts, documents, sorted(set(limits))


def previous_inventory(root):
    try:
        return small_json(confined_file(root, ".shippykit/discovery.json"))
    except (ValueError, OSError):
        return None


def next_actions(report):
    actions = []
    memory = [item for item in report["documents"] if item["role"] in ("app_facts", "checkpoints_and_decisions", "operation_or_section_journal", "existing_project_memory")]
    if memory:
        actions.append({"action": "read_existing_memory", "paths": [item["path"] for item in memory], "reason": "preserve_app_facts_owner_decisions_and_checkpoint_scope"})
    else:
        actions.append({"action": "establish_project_facts_from_existing_targets", "reason": "no_APP_or_STATE_memory_found; do_not_restart_existing_artifacts"})
    store_receipts = [item for item in report["receipts"] if item.get("observation_scope") == "store_operation"]
    if store_receipts:
        actions.append({"action": "reconcile_cached_operation", "paths": [item["path"] for item in store_receipts], "scope": "only_if_current_request_and_access_authorize_store_reads", "reason": "cached_receipts_do_not_prove_current_remote_state; read_before_retry"})
    issues = [item["path"] for manifest in report["manifests"] for item in manifest["entries"] if item.get("state") in ("missing", "changed") and "path" in item]
    if issues:
        actions.append({"action": "repair_only_affected_artifact_branch", "paths": issues, "reason": "missing_or_changed_local_evidence; retain_independent_valid_build_or_media_work"})
    if report["manifests"] or report["artifacts"]:
        actions.append({"action": "validate_artifacts_relevant_to_requested_stage", "reason": "select_intended_source_and_hashes_before_reusing_build_capture_or_upload_evidence; signing_is_unverified"})
    elif report["targets"]:
        actions.append({"action": "inspect_existing_build_commands_and_required_local_prerequisites", "reason": "target_files_exist_but_build_signing_and_device_readiness_are_unverified"})
    else:
        actions.append({"action": "select_actual_app_directory_or_inspect_scan_limits", "reason": "no_target_marker_found_within_bounded_project_scan"})
    return actions


def discover(project, verify_hashes=False):
    root = Path(project).expanduser().resolve(strict=True)
    if not root.is_dir():
        raise ValueError("Project must be a directory")
    budget = [MAX_HASH_TOTAL]
    source = git_summary(root)
    targets, clues, documents, releases, receipts, limits, scanned = scan_project(root, budget)
    manifests, artifacts = [], []
    for release in releases:
        found_manifests, found_receipts, found_artifacts, found_docs, found_limits = release_inventory(root, release, source, budget, verify_hashes)
        manifests.extend(found_manifests)
        receipts.extend(found_receipts)
        artifacts.extend(found_artifacts)
        documents.extend(found_docs)
        limits.extend(found_limits)
    previous = previous_inventory(root)
    if previous and previous.get("schema_version") == 1:
        old_documents = previous.get("documents", [])
        old = {item["path"]: item.get("sha256") for item in (old_documents if isinstance(old_documents, list) else []) if isinstance(item, dict) and isinstance(item.get("path"), str)}
        for item in documents:
            if item.get("sha256") and old.get(item["path"]) and old[item["path"]] != item["sha256"]:
                item.update(state="changed", reason="changed_since_discovery_snapshot")
    report = {
        "schema_version": 1, "observed_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "project": ".", "mode": "local_discovery", "remote_verified_now": False, "authorization": "not_inferred",
        "source": source, "targets": sorted(targets, key=lambda item: item["path"]), "framework_clues": clues,
        "documents": sorted(documents, key=lambda item: item["path"]), "manifests": manifests,
        "receipts": receipts, "artifacts": artifacts, "prior_discovery_snapshot": "present" if previous else "missing_or_unreadable",
        "limits": sorted(set(limits)), "scan": scanned, "hashes_requested": verify_hashes,
        "hash_bytes_read": MAX_HASH_TOTAL - budget[0],
        "scope_notes": ["Target markers and dependency declarations do not prove runnable platform builds.", "Git dirty summary covers tracked files only; untracked changes are not assessed.", "File presence and prior receipts never establish current store, device or signing state.", "No builds, network requests, installs or authorization decisions were performed."],
    }
    report["next_actions"] = next_actions(report)
    return report


def adopt(root, report):
    folder = confined_file(root, ".shippykit")
    if folder.exists() and not folder.is_dir():
        raise ValueError(".shippykit must be a directory")
    destination = confined_file(root, ".shippykit/discovery.json")
    if destination.exists():
        previous = small_json(destination)
        if previous.get("schema_version") != 1 or previous.get("mode") != "local_discovery":
            raise ValueError("Refusing to replace an unrecognized discovery file")
    folder.mkdir(mode=0o700, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".discovery-", suffix=".tmp", dir=str(folder))
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(report, stream, indent=2, ensure_ascii=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def text_report(report):
    lines = ["ShippyKit local discovery — current store/device state remains unverified."]
    source = report["source"]
    lines.append("Source: {} (tracked changes: {}; untracked changes: not assessed)".format(source.get("sha", source.get("reason", "unknown")), source.get("tracked_changes", "unknown")))
    for key, label in (("targets", "Targets"), ("framework_clues", "Framework clues"), ("documents", "Memory/documents"), ("manifests", "Manifests"), ("receipts", "Cached operation records"), ("artifacts", "Build candidates")):
        lines.append("{}: {}".format(label, len(report[key])))
        for item in report[key][:30]:
            lines.append("  {} — {}{}".format(item["path"], item.get("state", "unverified"), " / " + item.get("kind", item.get("framework", item.get("role", ""))) if item.get("kind") or item.get("framework") or item.get("role") else ""))
        if len(report[key]) > 30:
            lines.append("  More entries available with --json.")
    if report["limits"]:
        lines.append("Limits: " + ", ".join(report["limits"]))
    lines.append("Next: " + "; ".join(item["action"] for item in report["next_actions"]))
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("status", "adopt", "updates"))
    parser.add_argument("--project", default=".", help="Existing app directory; discovery never scans outside it")
    parser.add_argument("--json", action="store_true", help="Print sanitized structured inventory")
    parser.add_argument("--verify-hashes", action="store_true", help="Stream manifest SHA-256 checks within fixed file/total limits")
    args = parser.parse_args(argv)
    try:
        if args.command == "updates":
            report = check_updates(args.project)
            print(json.dumps(report, indent=2) if args.json else updates_text(report))
            return 0
        root = Path(args.project).expanduser().resolve(strict=True)
        report = discover(root, args.verify_hashes)
        if args.command == "adopt":
            adopt(root, report)
        print(json.dumps(report, indent=2) if args.json else text_report(report))
        return 0
    except (ValueError, OSError) as error:
        # Do not echo OS exception paths, which may expose a rejected secret reference.
        print(json.dumps({"error": str(error) if isinstance(error, ValueError) else "project_or_inventory_unavailable", "state": "unverified"}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
