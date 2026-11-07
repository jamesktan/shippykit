#!/usr/bin/env python3
"""App versions, build numbers and an evidence-backed changelog for ShippyKit.
Python 3.9+, standard library only.

Run `status` first and again after every step. It changes nothing and ends with one NEXT line:

    python3 deploy/versions.py status

Other commands:

    init      create CHANGELOG.md
    note      add a changelog entry with its evidence (commit, file or URL)
    set       change the version and/or build numbers in the native project files
    release   close [Unreleased] as the current version, with build numbers and upload evidence
    notes     print store "What's New" text for a version (no evidence links)

Rules: the marketing version is MAJOR.MINOR.PATCH (the first store release is 1.0.0) and is the
same on every platform; build numbers only go up; every changelog entry names its evidence.
Exit codes: 0 done, 2 another step is needed, 1 error.
"""
import argparse
import datetime
import os
from pathlib import Path
import re
import subprocess
import sys

VERSION_RE = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
SHA_RE = re.compile(r"^[0-9a-f]{7,40}$")
KINDS = ("Added", "Changed", "Fixed", "Removed", "Security", "Deprecated")
HEADER_RE = re.compile(r"^## \[(Unreleased|[^\]]+)\](?: - (\d{4}-\d{2}-\d{2}))?\s*$")
KIND_RE = re.compile(r"^### (\w+)\s*$")
EVIDENCE_RE = re.compile(r"\s*Evidence:\s*(.+?)\s*$")
BUILDS_RE = re.compile(r"^Builds:\s*(.+?)(?:\.\s*Evidence:\s*(.+?))?\s*$")
SKIP_DIRS = {".git", "node_modules", "Pods", "build", "builds", "DerivedData", ".gradle", "Library", "Temp", "release-output", ".shippykit", "vendor"}
STORE_LIMITS = {"apple": 4000, "google": 500}
EXIT_DONE, EXIT_ERROR, EXIT_NEXT = 0, 1, 2


def parse_version(text):
    m = VERSION_RE.match(text or "")
    return tuple(int(x) for x in m.groups()) if m else None


def suggested(text):
    """1.0 -> 1.0.0, 2 -> 2.0.0; None when it cannot be read as numbers."""
    parts = (text or "").strip().split(".")
    if not 1 <= len(parts) <= 3 or not all(p.isdigit() for p in parts):
        return None
    return ".".join(str(int(p)) for p in parts + ["0"] * (3 - len(parts)))


# ---------------------------------------------------------------- native project files


def walk(root, names, depth=5):
    root = Path(root)
    for current, dirs, files in os.walk(root):
        rel = Path(current).relative_to(root)
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".") and len(rel.parts) < depth]
        for name in files:
            if name in names:
                yield Path(current) / name


class Source:
    """One native file that holds a platform's marketing version and/or build number."""

    def __init__(self, root, path, platform, kind):
        self.root, self.path, self.platform, self.kind = Path(root), Path(path), platform, kind

    @property
    def rel(self):
        return str(self.path.relative_to(self.root))

    def read(self):
        text = self.path.read_text(errors="replace")
        return getattr(self, "read_" + self.kind)(text)

    def write(self, version=None, build=None):
        text = self.path.read_text()
        new = getattr(self, "write_" + self.kind)(text, version, build)
        if new != text:
            self.path.write_text(new)
        return new != text

    # Xcode: every build configuration carries its own copy.
    @staticmethod
    def read_pbxproj(text):
        versions = set(m.strip('"') for m in re.findall(r"MARKETING_VERSION = ([^;]+);", text))
        builds = set(m.strip('"') for m in re.findall(r"CURRENT_PROJECT_VERSION = ([^;]+);", text))
        return versions, builds

    @staticmethod
    def write_pbxproj(text, version, build):
        if version:
            text = re.sub(r'(MARKETING_VERSION = )("?)[^";]+("?);', lambda m: f"{m.group(1)}{m.group(2)}{version}{m.group(3)};", text)
        if build is not None:
            text = re.sub(r'(CURRENT_PROJECT_VERSION = )("?)[^";]+("?);', lambda m: f"{m.group(1)}{m.group(2)}{build}{m.group(3)};", text)
        return text

    # Info.plist with literal values (not $(MARKETING_VERSION) references).
    @staticmethod
    def read_plist(text):
        v = re.findall(r"<key>CFBundleShortVersionString</key>\s*<string>([^<$]+)</string>", text)
        b = re.findall(r"<key>CFBundleVersion</key>\s*<string>([^<$]+)</string>", text)
        return set(v), set(b)

    @staticmethod
    def write_plist(text, version, build):
        if version:
            text = re.sub(r"(<key>CFBundleShortVersionString</key>\s*<string>)[^<$]+(</string>)", lambda m: m.group(1) + version + m.group(2), text)
        if build is not None:
            text = re.sub(r"(<key>CFBundleVersion</key>\s*<string>)[^<$]+(</string>)", lambda m: m.group(1) + str(build) + m.group(2), text)
        return text

    # Android Gradle (Groovy or Kotlin DSL).
    @staticmethod
    def read_gradle(text):
        v = re.findall(r"\bversionName\s*=?\s*\"([^\"]+)\"", text)
        b = re.findall(r"\bversionCode\s*=?\s*(\d+)", text)
        return set(v), set(b)

    @staticmethod
    def write_gradle(text, version, build):
        if version:
            text = re.sub(r"(\bversionName\s*=?\s*\")[^\"]+(\")", lambda m: m.group(1) + version + m.group(2), text)
        if build is not None:
            text = re.sub(r"(\bversionCode\s*=?\s*)\d+", lambda m: m.group(1) + str(build), text)
        return text

    # Unity: one bundleVersion; per-platform build numbers.
    def read_unity(self, text):
        v = set(re.findall(r"(?m)^\s*bundleVersion: (.+?)\s*$", text))
        if self.platform == "ios":
            block = re.search(r"(?m)^\s*buildNumber:\s*\n((?:\s{4,}\w+: .*\n)+)", text)
            b = set(re.findall(r"(?m)^\s+iPhone: (\d+)\s*$", block.group(1))) if block else set()
        else:
            b = set(re.findall(r"(?m)^\s*AndroidBundleVersionCode: (\d+)\s*$", text))
        return v, b

    def write_unity(self, text, version, build):
        if version:
            text = re.sub(r"(?m)^(\s*bundleVersion: ).+?$", lambda m: m.group(1) + version, text)
        if build is not None:
            if self.platform == "ios":
                text = re.sub(r"(?m)(^\s*buildNumber:\s*\n(?:\s{4,}\w+: .*\n)*?\s+iPhone: )\d+", lambda m: m.group(1) + str(build), text)
            else:
                text = re.sub(r"(?m)^(\s*AndroidBundleVersionCode: )\d+", lambda m: m.group(1) + str(build), text)
        return text


def find_sources(root):
    sources = []
    for path in walk(root, {"project.pbxproj"}):
        text = path.read_text(errors="replace")
        if "MARKETING_VERSION" in text or "CURRENT_PROJECT_VERSION" in text:
            sources.append(Source(root, path, "ios", "pbxproj"))
    for path in walk(root, {"Info.plist"}):
        v, b = Source.read_plist(path.read_text(errors="replace"))
        if v or b:
            sources.append(Source(root, path, "ios", "plist"))
    for path in walk(root, {"build.gradle", "build.gradle.kts"}):
        text = path.read_text(errors="replace")
        if "applicationId" in text and ("versionCode" in text or "versionName" in text):
            sources.append(Source(root, path, "android", "gradle"))
    unity = Path(root) / "ProjectSettings" / "ProjectSettings.asset"
    if unity.is_file():
        sources += [Source(root, unity, "ios", "unity"), Source(root, unity, "android", "unity")]
    return sources


def platform_versions(sources):
    """{platform: {"versions": {...}, "builds": {...}, "files": [...]}}"""
    out = {}
    for s in sources:
        v, b = s.read()
        entry = out.setdefault(s.platform, {"versions": set(), "builds": set(), "files": []})
        entry["versions"] |= v
        entry["builds"] |= b
        entry["files"].append(s.rel)
    return out


# ---------------------------------------------------------------- changelog


class Changelog:
    def __init__(self, path):
        self.path = Path(path)
        self.lines = self.path.read_text().splitlines() if self.path.is_file() else []

    @property
    def exists(self):
        return self.path.is_file()

    def sections(self):
        """[(name, date, start, end)] in file order; end is exclusive."""
        found = [(i, HEADER_RE.match(line)) for i, line in enumerate(self.lines)]
        heads = [(i, m.group(1), m.group(2)) for i, m in found if m]
        return [(name, date, i, heads[k + 1][0] if k + 1 < len(heads) else len(self.lines)) for k, (i, name, date) in enumerate(heads)]

    def section(self, name):
        return next((s for s in self.sections() if s[0] == name), None)

    def entries(self, name):
        """[(line_no, kind, text, evidence_refs)] for one section."""
        s = self.section(name)
        if not s:
            return []
        kind, out = None, []
        for i in range(s[2] + 1, s[3]):
            line = self.lines[i]
            m = KIND_RE.match(line)
            if m:
                kind = m.group(1)
            elif line.startswith("- "):
                ev = EVIDENCE_RE.search(line)
                text = line[2:ev.start()] if ev else line[2:]
                refs = [r.strip() for r in ev.group(1).split(";") if r.strip()] if ev else []
                out.append((i + 1, kind, text.strip().rstrip("."), refs))
        return out

    def builds(self, name):
        s = self.section(name)
        for i in range(s[2] + 1, s[3]) if s else []:
            m = BUILDS_RE.match(self.lines[i])
            if m:
                return dict((p.split()[0].lower(), int(p.split()[1])) for p in m.group(1).split(",") if len(p.split()) == 2 and p.split()[1].isdigit())
        return {}

    def released(self):
        return [(name, date) for name, date, _, _ in self.sections() if name != "Unreleased"]

    def problems(self):
        out = []
        if not self.section("Unreleased"):
            out.append("missing the `## [Unreleased]` section")
        names = [n for n, _ in self.released()]
        for name, date in self.released():
            if not parse_version(name):
                out.append(f"version heading [{name}] is not MAJOR.MINOR.PATCH")
            if not date:
                out.append(f"version heading [{name}] has no date (`## [{name}] - YYYY-MM-DD`)")
        ordered = [parse_version(n) for n in names if parse_version(n)]
        if ordered != sorted(ordered, reverse=True):
            out.append("released versions are not listed newest first")
        for name, _, _, _ in self.sections():
            for line_no, kind, text, refs in self.entries(name):
                if kind not in KINDS:
                    out.append(f"line {line_no}: entry is not under one of ### {', '.join(KINDS)}")
                if not refs:
                    out.append(f"line {line_no}: entry has no `Evidence:` (add a commit, file or URL)")
                if not text:
                    out.append(f"line {line_no}: entry has no description")
        return out

    def save(self):
        self.path.write_text("\n".join(self.lines).rstrip() + "\n")


def check_ref(root, ref):
    """None when the evidence exists; otherwise why it does not."""
    if ref.startswith("https://"):
        return None
    if SHA_RE.match(ref):
        r = subprocess.run(["git", "-C", str(root), "cat-file", "-e", ref + "^{commit}"], capture_output=True)
        return None if r.returncode == 0 else f"commit {ref} is not in this repository"
    path = (Path(root) / ref).resolve()
    if Path(root).resolve() not in path.parents and path != Path(root).resolve():
        return f"{ref} is outside the project"
    return None if path.exists() else f"{ref} does not exist"


def head_commit(root):
    r = subprocess.run(["git", "-C", str(root), "rev-parse", "--short", "HEAD"], capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else None


def single(values):
    return next(iter(values)) if len(values) == 1 else None


# ---------------------------------------------------------------- status


def diagnose(root):
    checks = []

    def add(name, state, detail):
        checks.append({"check": name, "state": state, "detail": detail})

    platforms = platform_versions(find_sources(root))
    log = Changelog(Path(root) / "CHANGELOG.md")
    ctx = {"platforms": platforms, "log": log}
    if not platforms:
        add("native_versions", "missing", "no Xcode, Gradle or Unity version settings found")
        return checks, decide(checks, ctx, root)
    for name, p in sorted(platforms.items()):
        add(f"{name}_version", "ok" if len(p["versions"]) == 1 and parse_version(single(p["versions"])) else "wrong",
            f"version {', '.join(sorted(p['versions'])) or 'none'}, build {', '.join(sorted(p['builds'])) or 'none'} ({', '.join(p['files'])})")
    versions = {single(p["versions"]) for p in platforms.values()}
    ctx["version"] = single(versions) if None not in versions else None
    add("platforms_agree", "ok" if ctx["version"] else "wrong", " / ".join(f"{k} {', '.join(sorted(v['versions']))}" for k, v in sorted(platforms.items())))
    if not log.exists:
        add("changelog", "missing", "no CHANGELOG.md")
        return checks, decide(checks, ctx, root)
    problems = log.problems()
    add("changelog", "wrong" if problems else "ok", "; ".join(problems[:6]) or "format and evidence fields are complete")
    broken = [f"line {n}: {why}" for name, *_ in log.sections() for n, _, _, refs in log.entries(name) for why in [check_ref(root, r) for r in refs] if why]
    add("evidence", "wrong" if broken else "ok", "; ".join(broken[:6]) or "every reference exists")
    released = log.released()
    last = released[0][0] if released else None
    ctx.update(last=last, pending=log.entries("Unreleased"), broken=broken, problems=problems)
    add("release_state", "ok", f"last released {last or 'none'}; {len(ctx['pending'])} unreleased entr{'y' if len(ctx['pending']) == 1 else 'ies'}")
    if last:
        recorded = log.builds(last)
        stale = [f"{k} build {single(p['builds'])} is not above {recorded[k]} (released in {last})" for k, p in platforms.items()
                 if k in recorded and single(p["builds"]) and single(p["builds"]).isdigit() and int(single(p["builds"])) <= recorded[k]]
        ctx["stale_builds"] = stale
        add("build_numbers", "pending" if stale else "ok", "; ".join(stale) or "above the last release")
    return checks, decide(checks, ctx, root)


def decide(checks, ctx, root):
    s = {c["check"]: c["state"] for c in checks}

    def out(actor, message, command=None):
        return {"actor": actor, "message": message, "command": command}

    if s.get("native_versions") == "missing":
        return out("agent", "No native version settings were found. Record in deploy/APP.md where this app's version and build number live, and keep them as MAJOR.MINOR.PATCH and an integer build.")
    platforms = ctx["platforms"]
    for name, p in sorted(platforms.items()):
        if len(p["versions"]) == 1 and not parse_version(single(p["versions"])):
            fix = suggested(single(p["versions"]))
            if fix:
                return out("agent", f"The {name} version {single(p['versions'])!r} is not MAJOR.MINOR.PATCH. Set it to {fix} on every platform. It ships with the next build; if a store version record already exists, rename it to {fix} when that build is uploaded.",
                           f"python3 deploy/versions.py set --version {fix}")
        if len(p["versions"]) > 1:
            return out("agent", f"{name} files disagree on the version ({', '.join(sorted(p['versions']))}). Choose the right one and set it everywhere.", "python3 deploy/versions.py set --version <MAJOR.MINOR.PATCH>")
    if s.get("platforms_agree") == "wrong":
        top = max((v for p in platforms.values() for v in p["versions"] if parse_version(v)), key=parse_version, default=None)
        return out("agent", "The platforms have different versions. Use one version everywhere.", f"python3 deploy/versions.py set --version {top or '<MAJOR.MINOR.PATCH>'}")
    if s.get("changelog") == "missing":
        return out("agent", "Create the changelog.", "python3 deploy/versions.py init")
    if ctx["problems"] or ctx["broken"]:
        listing = "; ".join((ctx["problems"] + ctx["broken"])[:5])
        return out("agent", f"Fix CHANGELOG.md: {listing}. Each entry is one line `- What changed, for the user. Evidence: <commit>; <file>`. Then rerun status.")
    version, last, pending = ctx["version"], ctx["last"], ctx["pending"]
    if last and version == last and pending:
        bump = "minor" if any(k in ("Added", "Changed", "Removed", "Deprecated") for _, k, _, _ in pending) else "patch"
        return out("agent", f"{version} is already released and there are unreleased changes. Raise the version before the next build ({bump}: new or changed features raise MINOR, fixes raise PATCH; only the owner decides on a new MAJOR).",
                   f"python3 deploy/versions.py set --bump {bump} --next-build")
    if last and parse_version(version) < parse_version(last):
        return out("agent", f"The project version {version} is lower than the released {last}. Set a version above {last}.", "python3 deploy/versions.py set --version <higher MAJOR.MINOR.PATCH>")
    if ctx.get("stale_builds") and version != last:
        return out("agent", "Build numbers must go up for every upload: " + "; ".join(ctx["stale_builds"]) + ".", "python3 deploy/versions.py set --next-build")
    if not pending and version != last:
        return out("agent", f"{version} has no changelog entries yet. Add at least one entry for what this release brings, with its evidence.",
                   f"python3 deploy/versions.py note --kind Added --text \"<what changed, for the user>\" --evidence {head_commit(root) or '<commit>'}")
    if pending and version != last:
        builds = ", ".join(f"{k} {single(p['builds'])}" for k, p in sorted(ctx["platforms"].items()) if single(p["builds"]))
        return out("done", f"{version} is in progress with {len(pending)} entr{'y' if len(pending) == 1 else 'ies'}. Keep adding entries with `versions.py note` as changes land. Each store upload needs a build number the store has not seen (now {builds or 'unknown'}); raise them with `versions.py set --next-build` before building if this one was already uploaded. After the upload is accepted, run `python3 deploy/versions.py release --evidence <upload receipt>`.")
    return out("done", f"{version} is released and recorded. Add entries with `versions.py note` as changes land; status will say when to raise the version.")


def print_status(checks, nxt):
    for c in checks:
        print(f"  {c['state']:<8} {c['check']}: {c['detail']}")
    print(f"NEXT [{nxt['actor']}]: {nxt['message']}")
    if nxt.get("command"):
        print(f"  $ {nxt['command']}")


# ---------------------------------------------------------------- commands


def cmd_status(args):
    checks, nxt = diagnose(args.root)
    print_status(checks, nxt)
    return EXIT_DONE if nxt["actor"] == "done" else EXIT_NEXT


def cmd_init(args):
    path = Path(args.root) / "CHANGELOG.md"
    if path.exists():
        print("CHANGELOG.md already exists; nothing changed.")
        return EXIT_DONE
    name = args.app or Path(args.root).resolve().name
    path.write_text(f"""# Changelog

Notable changes to {name}, newest first. Versions are MAJOR.MINOR.PATCH and every entry ends with its evidence: a commit, a file in this repository, or a URL. `python3 deploy/versions.py` maintains and checks this file.

## [Unreleased]
""")
    print(f"Created CHANGELOG.md. NEXT: python3 deploy/versions.py status")
    return EXIT_DONE


def cmd_note(args):
    root, log = Path(args.root), Changelog(Path(args.root) / "CHANGELOG.md")
    kind = args.kind.capitalize()
    if kind not in KINDS:
        print(f"--kind must be one of {', '.join(KINDS)}")
        return EXIT_ERROR
    text = " ".join(args.text.split()).rstrip(".")
    if not text or "Evidence:" in text:
        print("--text is the change in plain words, without the evidence (pass that with --evidence).")
        return EXIT_ERROR
    refs = args.evidence or []
    if not refs:
        print("Pass at least one --evidence: a commit SHA, a file path in this repository, or an https:// URL.")
        return EXIT_ERROR
    bad = [why for why in (check_ref(root, r) for r in refs) if why]
    if bad:
        print("Evidence not found: " + "; ".join(bad))
        return EXIT_ERROR
    if not log.exists:
        print("No CHANGELOG.md yet. Run: python3 deploy/versions.py init")
        return EXIT_NEXT
    section = log.section("Unreleased")
    if not section:
        print("CHANGELOG.md has no `## [Unreleased]` section; add it under the title, then rerun.")
        return EXIT_ERROR
    line = f"- {text}. Evidence: {'; '.join(refs)}"
    if any(l.strip() == line for l in log.lines):
        print("That entry is already in the changelog.")
        return EXIT_DONE
    _, _, start, end = section
    heading = next((i for i in range(start + 1, end) if log.lines[i].strip() == f"### {kind}"), None)
    if heading is None:
        insert = end
        while insert > start + 1 and not log.lines[insert - 1].strip():
            insert -= 1
        log.lines[insert:insert] = ["", f"### {kind}", line]
    else:
        insert = heading + 1
        while insert < end and log.lines[insert].startswith("- "):
            insert += 1
        log.lines.insert(insert, line)
    log.save()
    print(f"Added under [Unreleased] › {kind}: {line}")
    return EXIT_DONE


def cmd_set(args):
    root = Path(args.root)
    sources = find_sources(root)
    if not sources:
        print("No Xcode, Gradle or Unity version settings found.")
        return EXIT_ERROR
    platforms = platform_versions(sources)
    target = args.version
    if args.bump:
        current = {single(p["versions"]) for p in platforms.values()}
        base = parse_version(single(current) or "") or parse_version(suggested(single(current) or "") or "")
        if not base:
            print("The platforms disagree on the version; pass --version instead of --bump.")
            return EXIT_ERROR
        major, minor, patch = base
        if args.bump == "major" and not args.owner_approved_major:
            print("A new MAJOR version is the owner's decision. Rerun with --owner-approved-major once they have said so.")
            return EXIT_ERROR
        target = {"major": f"{major + 1}.0.0", "minor": f"{major}.{minor + 1}.0", "patch": f"{major}.{minor}.{patch + 1}"}[args.bump]
    if target and not parse_version(target):
        print(f"{target!r} is not MAJOR.MINOR.PATCH (for example 1.0.0).")
        return EXIT_ERROR
    log = Changelog(root / "CHANGELOG.md")
    released = log.released() if log.exists else []
    if target and released and parse_version(released[0][0]) and parse_version(target) <= parse_version(released[0][0]):
        print(f"{target} is not above the last released version {released[0][0]}.")
        return EXIT_ERROR
    builds = {}
    for name, p in platforms.items():
        numbers = [int(b) for b in p["builds"] if b.isdigit()]
        recorded = log.builds(released[0][0]).get(name, 0) if released else 0
        if args.build:
            wanted = dict(item.split("=", 1) for item in args.build)
            if name in wanted:
                builds[name] = int(wanted[name])
        elif args.next_build:
            builds[name] = max(numbers + [recorded]) + 1
        if name in builds and builds[name] <= max(numbers + [recorded], default=0) and not args.build:
            print(f"{name}: the next build must be above {max(numbers + [recorded])}.")
            return EXIT_ERROR
        if name in builds and numbers and builds[name] < max(numbers):
            print(f"{name}: build numbers only go up (current {max(numbers)}).")
            return EXIT_ERROR
    if not target and not builds:
        print("Nothing to change: pass --version, --bump, --next-build or --build ios=N.")
        return EXIT_ERROR
    changed = [s.rel for s in sources if s.write(target, builds.get(s.platform))]
    after = platform_versions(find_sources(root))
    for name, p in after.items():
        if target and p["versions"] != {target}:
            print(f"ERROR: {name} still reads {sorted(p['versions'])} after the change ({', '.join(p['files'])}).")
            return EXIT_ERROR
        if name in builds and p["builds"] != {str(builds[name])}:
            print(f"ERROR: {name} build reads {sorted(p['builds'])} after the change.")
            return EXIT_ERROR
    print("Updated " + (", ".join(changed) or "nothing (already set)") + ".")
    for name, p in sorted(after.items()):
        print(f"  {name}: version {single(p['versions'])}, build {single(p['builds'])}")
    print("NEXT: python3 deploy/versions.py status")
    return EXIT_DONE


def cmd_release(args):
    root = Path(args.root)
    checks, nxt = diagnose(root)
    log = Changelog(root / "CHANGELOG.md")
    platforms = platform_versions(find_sources(root))
    versions = {single(p["versions"]) for p in platforms.values()}
    version = single(versions)
    if not log.exists or not version or not parse_version(version):
        print("Run `python3 deploy/versions.py status` and fix what it reports first.")
        return EXIT_NEXT
    problems = log.problems() + [c["detail"] for c in checks if c["check"] == "evidence" and c["state"] != "ok"]
    if problems:
        print("Fix CHANGELOG.md first: " + "; ".join(problems[:5]))
        return EXIT_NEXT
    pending = log.entries("Unreleased")
    if not pending:
        print(f"[Unreleased] is empty; add what {version} brings with `versions.py note` first.")
        return EXIT_NEXT
    released = log.released()
    if released and parse_version(version) <= parse_version(released[0][0]):
        print(f"The project version {version} is not above the last release {released[0][0]}. Run `versions.py set --bump patch` (or minor).")
        return EXIT_NEXT
    refs = args.evidence or []
    bad = [why for why in (check_ref(root, r) for r in refs) if why]
    if not refs or bad:
        print("Pass the upload evidence with --evidence (for example release-output/apple-upload-receipt.json)." + (" Not found: " + "; ".join(bad) if bad else ""))
        return EXIT_ERROR
    builds = ", ".join(f"{'iOS' if k == 'ios' else 'Android'} {single(p['builds'])}" for k, p in sorted(platforms.items()) if single(p["builds"]))
    date = args.date or datetime.date.today().isoformat()
    _, _, start, _ = log.section("Unreleased")
    log.lines[start:start + 1] = ["## [Unreleased]", "", f"## [{version}] - {date}", "", f"Builds: {builds}. Evidence: {'; '.join(refs)}"]
    log.save()
    print(f"Recorded {version} ({builds}) with {len(pending)} entr{'y' if len(pending) == 1 else 'ies'}. Store text: python3 deploy/versions.py notes --store apple")
    return EXIT_DONE


def cmd_notes(args):
    log = Changelog(Path(args.root) / "CHANGELOG.md")
    released = log.released() if log.exists else []
    name = args.version or (released[0][0] if released else "Unreleased")
    entries = log.entries(name)
    if not entries:
        print(f"No entries for [{name}].")
        return EXIT_ERROR
    order = {k: i for i, k in enumerate(("Added", "Changed", "Fixed", "Security", "Removed", "Deprecated"))}
    lines = [f"• {text}." for _, kind, text, _ in sorted(entries, key=lambda e: order.get(e[1], 9))]
    body = "\n".join(lines)
    print(body)
    limit = STORE_LIMITS.get(args.store or "")
    if limit and len(body) > limit:
        print(f"\nERROR: {len(body)} characters; the {args.store} limit is {limit}. Shorten the entries in CHANGELOG.md or pick the most important ones for the store.", file=sys.stderr)
        return EXIT_ERROR
    return EXIT_DONE


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=("status", "init", "note", "set", "release", "notes"))
    parser.add_argument("--root", default=".", help="app repository (default: current directory)")
    parser.add_argument("--app", help="init: app name for the title")
    parser.add_argument("--kind", default="Changed", help=f"note: one of {', '.join(KINDS)}")
    parser.add_argument("--text", help="note: the change, in words a user understands")
    parser.add_argument("--evidence", action="append", help="note/release: commit SHA, file path or https URL (repeatable)")
    parser.add_argument("--version", help="set: new MAJOR.MINOR.PATCH; notes: which version (default: latest)")
    parser.add_argument("--bump", choices=("major", "minor", "patch"), help="set: raise the version")
    parser.add_argument("--owner-approved-major", action="store_true", help="set: the owner approved a new MAJOR version")
    parser.add_argument("--next-build", action="store_true", help="set: raise every platform's build number by one above the highest seen")
    parser.add_argument("--build", action="append", help="set: explicit build, e.g. ios=18 or android=4")
    parser.add_argument("--date", help="release: date (default today)")
    parser.add_argument("--store", choices=("apple", "google"), help="notes: check that store's length limit")
    args = parser.parse_args(argv)
    if args.command == "note" and not args.text:
        parser.error("note needs --text")
    return {"status": cmd_status, "init": cmd_init, "note": cmd_note, "set": cmd_set, "release": cmd_release, "notes": cmd_notes}[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
