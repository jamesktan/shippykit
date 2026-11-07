#!/usr/bin/env python3
"""Install ShippyKit locally while preserving project memory and customizations.

Python 3.9+; standard library only. No network, build, credentials, or store calls.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys
import tempfile


RECEIPT = ".shippykit/install.json"
PROTECTED = {"deploy/APP.md", "deploy/STATE.md"}
SKIP_DIRS = {"__pycache__", "node_modules"}
PRIVATE_SUFFIXES = {".p8", ".p12", ".pfx", ".pem", ".key", ".keystore", ".jks",
                    ".mobileprovision", ".ipa", ".aab", ".apk", ".xcarchive"}
AGENTS = {"codex": (".agents/skills", "AGENTS.md"),
          "claude": (".claude/skills", "CLAUDE.md")}
MARKERS = ("<!-- shippykit:begin -->", "<!-- shippykit:end -->")
IGNORE_MARKERS = ("# >>> ShippyKit managed ignores >>>",
                  "# <<< ShippyKit managed ignores <<<")


class InstallError(Exception):
    """Unsafe or malformed input; refuse before modifying the project."""


def digest(data):
    return hashlib.sha256(data).hexdigest()


def relative_path(value):
    if not isinstance(value, str) or not value or any(char in value for char in ("\\", ":", "\0")):
        raise InstallError("Receipt contains an invalid relative path")
    p = PurePosixPath(value)
    if p.is_absolute() or any(part in (".", "..") for part in value.split("/")) or "" in value.split("/"):
        raise InstallError("Path must stay inside the selected project: " + value)
    return p


def safe_path(project, relative):
    """Check every component before reading, hashing, creating, or replacing it."""
    if project.is_symlink() or (project.exists() and not project.is_dir()):
        raise InstallError("Project root is no longer a regular directory")
    parts = relative_path(relative).parts
    current = project
    for index, part in enumerate(parts):
        current = current / part
        if current.is_symlink():
            raise InstallError("Symlink in destination path: " + relative)
        if current.exists():
            mode = current.stat().st_mode
            if index < len(parts) - 1 and not stat.S_ISDIR(mode):
                raise InstallError("Destination parent is not a directory: " + relative)
            if index == len(parts) - 1 and not stat.S_ISREG(mode):
                raise InstallError("Destination is not a regular file: " + relative)
    return current


def source_files(package):
    """Explicitly walk only package deploy/ and skills/, plus LICENSE; never follow links."""
    result = {}

    def walk(directory):
        for path in sorted(directory.iterdir(), key=lambda item: item.name):
            if path.is_symlink():
                raise InstallError("Symlink in package source: " + path.relative_to(package).as_posix())
            if path.name.startswith(".") or path.name in SKIP_DIRS or path.suffix in {".pyc", ".pyo"}:
                continue
            if path.suffix.lower() in PRIVATE_SUFFIXES or path.name in {"private", "release-output"}:
                raise InstallError("Sensitive/generated artifact in package source: " + path.relative_to(package).as_posix())
            if path.is_dir():
                walk(path)
            elif path.is_file():
                result[path.relative_to(package).as_posix()] = (path.read_bytes(), stat.S_IMODE(path.stat().st_mode))
            else:
                raise InstallError("Non-regular package source: " + path.relative_to(package).as_posix())

    for name in ("deploy", "skills"):
        directory = package / name
        if directory.is_symlink() or not directory.is_dir():
            raise InstallError("Package requires a regular " + name + " directory")
        walk(directory)
    license_path = package / "LICENSE"
    if license_path.is_symlink():
        raise InstallError("Symlink in package source: LICENSE")
    if license_path.is_file():
        # Installed copies keep the MIT notice beside the files they came from.
        result["deploy/LICENSE"] = (license_path.read_bytes(), stat.S_IMODE(license_path.stat().st_mode))
    for required in ("deploy/README.md", "deploy/APP.md", "deploy/STATE.md",
                     "deploy/RESUME.md", "deploy/shippykit.py",
                     "skills/shippykit/SKILL.md", "skills/shippykit-images/SKILL.md",
                     "skills/shippykit-store-copy/SKILL.md"):
        if required not in result:
            raise InstallError("Package is missing " + required)
    return result


def read_receipt(project):
    path = safe_path(project, RECEIPT)
    if not path.exists():
        return {}
    try:
        receipt = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, UnicodeError) as error:
        raise InstallError("Cannot read existing install receipt; preserve it and resolve the error") from error
    if not isinstance(receipt, dict) or receipt.get("schema_version") != 1:
        raise InstallError("Unsupported install receipt schema")
    for key in ("source_files", "managed_files", "managed_blocks", "incoming_files"):
        mapping = receipt.get(key, {})
        if not isinstance(mapping, dict):
            raise InstallError("Invalid receipt mapping: " + key)
        for name, sha in mapping.items():
            relative_path(name)
            if not isinstance(sha, str) or not re.fullmatch(r"[a-f0-9]{64}", sha):
                raise InstallError("Invalid receipt hash: " + key)
    agents = receipt.get("installed_agents", [])
    if not isinstance(agents, list) or any(agent not in AGENTS for agent in agents):
        raise InstallError("Invalid agent list in receipt")
    conflicts = receipt.get("conflicts", [])
    if not isinstance(conflicts, list):
        raise InstallError("Invalid conflict list in receipt")
    for conflict in conflicts:
        if not isinstance(conflict, dict):
            raise InstallError("Invalid conflict entry in receipt")
        for key in ("path", "incoming"):
            relative_path(conflict.get(key))
        for key in ("current_sha256", "upstream_sha256"):
            if not isinstance(conflict.get(key), str) or not re.fullmatch(r"[a-f0-9]{64}", conflict[key]):
                raise InstallError("Invalid conflict hash in receipt")
    return receipt


def instruction_block(agent):
    skills = AGENTS[agent][0]
    invocation = "$shippykit" if agent == "codex" else "/shippykit"
    return (MARKERS[0] + "\n"
            "## ShippyKit\n\n"
            "When asked to install, run, or resume ShippyKit, use " + invocation +
            " ([skill](" + skills + "/shippykit/SKILL.md)).\n"
            "Start with [deploy/README.md](deploy/README.md) and "
            "[deploy/RESUME.md](deploy/RESUME.md); preserve existing "
            "[APP.md](deploy/APP.md), [STATE.md](deploy/STATE.md), journals, "
            "and the user's recorded scope.\n"
            "“Resume ShippyKit” continues from that evidence. Installation alone "
            "does not authorize builds, tool installation, store changes, or release.\n" +
            MARKERS[1]).encode("utf-8")


class Planner:
    def __init__(self, project, receipt):
        self.project = project
        self.managed = dict(receipt.get("managed_files", {}))
        self.blocks = dict(receipt.get("managed_blocks", {}))
        self.incoming = dict(receipt.get("incoming_files", {}))
        self.touched = set()
        self.operations = {}
        self.summary = {"installed": [], "updated": [], "preserved": [], "conflicts": []}

    def existing(self, relative):
        path = safe_path(self.project, relative)
        return path.read_bytes() if path.exists() else None

    def write(self, relative, data, mode=0o644):
        safe_path(self.project, relative)
        if relative in self.operations and self.operations[relative][0] != data:
            raise InstallError("Package destination collision: " + relative)
        self.operations[relative] = (data, mode)

    def conflict(self, relative, current, incoming, reason):
        sha = digest(incoming)
        candidate = ".shippykit/incoming/" + relative
        old = self.existing(candidate)
        if old is not None and digest(old) != sha and self.incoming.get(candidate) != digest(old):
            # Preserve a manually edited candidate as carefully as the live file.
            candidate += ".upstream-" + sha
            old = self.existing(candidate)
            if old is not None and digest(old) != sha:
                raise InstallError("Customized incoming candidate cannot be replaced: " + candidate)
        if old != incoming:
            self.write(candidate, incoming)
        self.incoming[candidate] = sha
        self.summary["conflicts"].append({"path": relative, "reason": reason,
                                          "current_sha256": digest(current),
                                          "upstream_sha256": sha, "incoming": candidate})

    def install_file(self, relative, data, mode):
        self.touched.add(relative)
        current = self.existing(relative)
        sha = digest(data)
        if current is None:
            self.write(relative, data, mode)
            self.managed[relative] = sha
            self.summary["installed"].append(relative)
        elif relative in PROTECTED:
            self.summary["preserved"].append(relative)
            # These are app memory, even when their original template was managed.
            if self.managed.get(relative) == digest(current) or current == data:
                self.managed[relative] = digest(current)
        elif current == data:
            self.managed[relative] = sha
            self.summary["preserved"].append(relative)
        elif self.managed.get(relative) == digest(current):
            self.write(relative, data, mode)
            self.managed[relative] = sha
            self.summary["updated"].append(relative)
        else:
            self.summary["preserved"].append(relative)
            self.conflict(relative, current, data, "existing_file_modified_or_unmanaged")

    def merge_block(self, relative, incoming, markers):
        self.touched.add(relative)
        current = self.existing(relative)
        current = b"" if current is None else current
        begin, end = (value.encode("utf-8") for value in markers)
        if begin not in current and end not in current:
            separator = b"" if not current else (b"\n" if current.endswith(b"\n") else b"\n\n")
            result = current + separator + incoming + b"\n"
        elif current.count(begin) == current.count(end) == 1 and current.index(begin) < current.index(end):
            start = current.index(begin)
            finish = current.index(end) + len(end)
            existing = current[start:finish]
            if existing == incoming:
                self.blocks[relative] = digest(incoming)
                self.summary["preserved"].append(relative)
                return
            if self.blocks.get(relative) != digest(existing):
                self.summary["preserved"].append(relative)
                self.conflict(relative, current, incoming + b"\n", "managed_block_modified_or_unmanaged")
                return
            result = current[:start] + incoming + current[finish:]
        else:
            self.summary["preserved"].append(relative)
            self.conflict(relative, current, incoming + b"\n", "ambiguous_managed_block_markers")
            return
        path = safe_path(self.project, relative)
        mode = stat.S_IMODE(path.stat().st_mode) if path.exists() else 0o644
        self.write(relative, result, mode)
        self.blocks[relative] = digest(incoming)
        self.summary["updated" if path.exists() else "installed"].append(relative)


def atomic_write(project, relative, data, mode):
    path = safe_path(project, relative)
    path.parent.mkdir(parents=True, exist_ok=True)
    safe_path(project, relative)
    descriptor, temporary = tempfile.mkstemp(prefix=".shippykit-write-", dir=str(path.parent))
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
        os.chmod(temporary, mode & 0o777)
        safe_path(project, relative)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def install(package, target, agent="both", dry_run=False):
    package = Path(package).absolute()
    target = Path(target).expanduser().absolute()
    if package.is_symlink() or target.is_symlink():
        raise InstallError("Package and project roots must not be symlinks")
    package = package.resolve()
    project = target.resolve()
    if project == Path(project.anchor) or project == Path.home().resolve():
        raise InstallError("Choose an app project directory, not a filesystem or home root")
    if project == package or package in project.parents or project in package.parents:
        raise InstallError("Project and package source must not overlap")
    if project.exists() and not project.is_dir():
        raise InstallError("Project root must be a directory")
    version_path = package / "VERSION"
    if version_path.is_symlink() or not version_path.is_file():
        raise InstallError("Package VERSION must be a regular file")
    version = version_path.read_text(encoding="utf-8").strip()
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+(?:[-+][A-Za-z0-9.-]+)?", version):
        raise InstallError("Package VERSION must contain a version number")
    if agent not in ("codex", "claude", "both"):
        raise InstallError("Unknown agent selection")
    selected = list(AGENTS) if agent == "both" else [agent]
    files = source_files(package)
    previous = read_receipt(project)
    planner = Planner(project, previous)
    for name, (data, mode) in files.items():
        if name.startswith("deploy/"):
            planner.install_file(name, data, mode)
        else:
            for chosen in selected:
                destination = AGENTS[chosen][0] + "/" + name[len("skills/"):]
                planner.install_file(destination, data, mode)
    for chosen in selected:
        planner.merge_block(AGENTS[chosen][1], instruction_block(chosen), MARKERS)
    ignore = (IGNORE_MARKERS[0] + "\n/.shippykit/incoming/\n/.shippykit/discovery.json\n"
              "/deploy/__pycache__/\n" + IGNORE_MARKERS[1]).encode("utf-8")
    planner.merge_block(".gitignore", ignore, IGNORE_MARKERS)
    # A Codex-only refresh must not forget an unresolved Claude customization,
    # nor should removal from a later package erase a previously recorded conflict.
    planner.summary["conflicts"].extend(conflict for conflict in previous.get("conflicts", [])
                                        if conflict["path"] not in planner.touched)
    receipt = {"schema_version": 1, "package_version": version,
               "installed_agents": sorted(set(previous.get("installed_agents", [])) | set(selected)),
               "source_files": {name: digest(value[0]) for name, value in sorted(files.items())},
               "managed_files": dict(sorted(planner.managed.items())),
               "managed_blocks": dict(sorted(planner.blocks.items())),
               "incoming_files": dict(sorted(planner.incoming.items())),
               "conflicts": planner.summary["conflicts"]}
    receipt_bytes = (json.dumps(receipt, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    if planner.existing(RECEIPT) != receipt_bytes:
        planner.write(RECEIPT, receipt_bytes)
    if not dry_run:
        project.mkdir(parents=True, exist_ok=True)
        # The receipt is deliberately last; an interrupted run never adopts unwritten bytes.
        for relative, (data, mode) in planner.operations.items():
            atomic_write(project, relative, data, mode)
    return {"package_version": version, "dry_run": dry_run,
            **planner.summary, "receipt": RECEIPT, "next": "Resume ShippyKit"}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", nargs="?", default=os.getcwd(), help="App project (default: caller's current directory)")
    parser.add_argument("--dry-run", action="store_true", help="Show planned results without writing anything")
    parser.add_argument("--agent", choices=("codex", "claude", "both"), default="both")
    args = parser.parse_args(argv)
    try:
        if Path(__file__).is_symlink():
            raise InstallError("Installer source must not be a symlink")
        result = install(Path(__file__).parent, args.project, args.agent, args.dry_run)
    except (InstallError, OSError, UnicodeError) as error:
        print("ShippyKit install refused: " + str(error), file=sys.stderr)
        return 2
    print("ShippyKit " + result["package_version"] + (" dry run" if args.dry_run else " installed"))
    for key in ("installed", "updated", "preserved", "conflicts"):
        print(key.capitalize() + ": " + str(len(result[key])))
    for conflict in result["conflicts"]:
        print("Preserved " + conflict["path"] + "; upstream candidate: " + conflict["incoming"])
    print("Next: " + result["next"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
