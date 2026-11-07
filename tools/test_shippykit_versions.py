"""versions.py against temporary Xcode, Gradle and Unity projects in throwaway git repositories."""
import contextlib
import importlib.util
import io
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True
HELPER = Path(__file__).resolve().parents[1] / "docs/launch/harness/deploy/versions.py"
SPEC = importlib.util.spec_from_file_location("shippykit_versions", HELPER)
versions = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(versions)

PBXPROJ = """// !$*UTF8*$!
{{
\t\tbuildSettings = {{
\t\t\tCURRENT_PROJECT_VERSION = {build};
\t\t\tMARKETING_VERSION = {version};
\t\t}};
\t\tbuildSettings = {{
\t\t\tCURRENT_PROJECT_VERSION = {build};
\t\t\tMARKETING_VERSION = {version};
\t\t}};
}}
"""
GRADLE = """android {{
    defaultConfig {{
        applicationId "com.example.app"
        versionCode {build}
        versionName "{version}"
    }}
}}
"""
GRADLE_KTS = """android {{
    defaultConfig {{
        applicationId = "com.example.app"
        versionCode = {build}
        versionName = "{version}"
    }}
}}
"""
UNITY = """PlayerSettings:
  bundleVersion: {version}
  applicationIdentifier:
    iPhone: com.example.app
  buildNumber:
    Standalone: 0
    VisionOS: 0
    iPhone: {ios}
    tvOS: 0
  AndroidBundleVersionCode: {android}
  someOtherBlock:
    iPhone: 1
"""


def cli(root, *argv):
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
        code = versions.main([argv[0], "--root", str(root), *argv[1:]])
    return code, out.getvalue()


class Project:
    def __init__(self, test):
        self.tmp = tempfile.TemporaryDirectory()
        test.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.git("init", "-q")
        self.git("config", "user.email", "test@example.com")
        self.git("config", "user.name", "Test")

    def git(self, *args):
        return subprocess.run(["git", "-C", str(self.root), *args], capture_output=True, text=True, check=True).stdout.strip()

    def write(self, rel, text):
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        return path

    def commit(self, message="change"):
        self.git("add", "-A")
        self.git("commit", "-q", "-m", message, "--allow-empty")
        return self.git("rev-parse", "--short", "HEAD")

    def capacitor(self, version="1.0", ios=17, android=3, quoted=False):
        v = f'"{version}"' if quoted else version
        self.write("mobile/ios/App/App.xcodeproj/project.pbxproj", PBXPROJ.format(version=v, build=ios))
        self.write("mobile/android/app/build.gradle", GRADLE.format(version=version, build=android))
        self.write("node_modules/plugin/android/build.gradle", GRADLE.format(version="9.9", build=99))
        return self


class DetectionTests(unittest.TestCase):
    def test_reads_xcode_gradle_and_ignores_dependencies(self):
        p = Project(self).capacitor()
        found = versions.platform_versions(versions.find_sources(p.root))
        self.assertEqual(found["ios"]["versions"], {"1.0"})
        self.assertEqual(found["ios"]["builds"], {"17"})
        self.assertEqual(found["android"]["versions"], {"1.0"})
        self.assertEqual(found["android"]["builds"], {"3"})
        self.assertEqual(found["android"]["files"], ["mobile/android/app/build.gradle"])
        self.assertEqual(found["ios"]["files"], ["mobile/ios/App/App.xcodeproj/project.pbxproj"])

    def test_reads_unity_per_platform_builds_and_kotlin_gradle(self):
        p = Project(self)
        p.write("ProjectSettings/ProjectSettings.asset", UNITY.format(version="1.0", ios=9, android=1))
        found = versions.platform_versions(versions.find_sources(p.root))
        self.assertEqual((found["ios"]["builds"], found["android"]["builds"]), ({"9"}, {"1"}))
        q = Project(self)
        q.write("app/build.gradle.kts", GRADLE_KTS.format(version="2.1.0", build=40))
        self.assertEqual(versions.platform_versions(versions.find_sources(q.root))["android"]["builds"], {"40"})


class StatusTests(unittest.TestCase):
    def test_two_part_version_is_fixed_to_three_parts_everywhere(self):
        p = Project(self).capacitor()
        code, out = cli(p.root, "status")
        self.assertEqual(code, versions.EXIT_NEXT)
        self.assertIn("$ python3 deploy/versions.py set --version 1.0.0", out)
        code, out = cli(p.root, "set", "--version", "1.0.0")
        self.assertEqual(code, 0, out)
        self.assertIn("MARKETING_VERSION = 1.0.0;", (p.root / "mobile/ios/App/App.xcodeproj/project.pbxproj").read_text())
        self.assertIn('versionName "1.0.0"', (p.root / "mobile/android/app/build.gradle").read_text())
        self.assertIn('versionName "9.9"', (p.root / "node_modules/plugin/android/build.gradle").read_text())

    def test_quoted_xcode_values_keep_their_quotes(self):
        p = Project(self).capacitor(version="1.0.0", quoted=True)
        cli(p.root, "set", "--version", "1.0.1")
        self.assertIn('MARKETING_VERSION = "1.0.1";', (p.root / "mobile/ios/App/App.xcodeproj/project.pbxproj").read_text())

    def test_platforms_that_disagree_are_reported(self):
        p = Project(self).capacitor(version="1.0.0")
        p.write("mobile/android/app/build.gradle", GRADLE.format(version="1.1.0", build=3))
        code, out = cli(p.root, "status")
        self.assertIn("different versions", out)
        self.assertIn("set --version 1.1.0", out)

    def test_full_cycle_init_note_release_then_bump(self):
        p = Project(self).capacitor(version="1.0.0")
        sha = p.commit("first playable")
        self.assertIn("versions.py init", cli(p.root, "status")[1])
        self.assertEqual(cli(p.root, "init", "--app", "Example")[0], 0)
        code, out = cli(p.root, "status")
        self.assertIn("has no changelog entries yet", out)
        self.assertIn(f"--evidence {sha}", out)
        p.write("release-output/results/tests.txt", "46 passed\n")
        code, out = cli(p.root, "note", "--kind", "added", "--text", "Three random specials per game.", "--evidence", sha, "--evidence", "release-output/results/tests.txt")
        self.assertEqual(code, 0, out)
        log = (p.root / "CHANGELOG.md").read_text()
        self.assertIn(f"### Added\n- Three random specials per game. Evidence: {sha}; release-output/results/tests.txt", log)
        code, out = cli(p.root, "status")
        self.assertEqual(code, versions.EXIT_DONE, out)
        self.assertIn("in progress", out)
        self.assertEqual(cli(p.root, "release")[0], versions.EXIT_ERROR, "release needs upload evidence")
        p.write("release-output/apple-upload-receipt.json", "{}")
        code, out = cli(p.root, "release", "--evidence", "release-output/apple-upload-receipt.json", "--date", "2026-10-29")
        self.assertEqual(code, 0, out)
        log = (p.root / "CHANGELOG.md").read_text()
        self.assertIn("## [Unreleased]\n\n## [1.0.0] - 2026-10-29\n\nBuilds: Android 3, iOS 17. Evidence: release-output/apple-upload-receipt.json", log)
        self.assertEqual(cli(p.root, "status")[0], versions.EXIT_DONE)
        fix = p.commit("fix crash")
        cli(p.root, "note", "--kind", "Fixed", "--text", "No crash when the board fills", "--evidence", fix)
        code, out = cli(p.root, "status")
        self.assertIn("$ python3 deploy/versions.py set --bump patch --next-build", out)
        code, out = cli(p.root, "set", "--bump", "patch", "--next-build")
        self.assertEqual(code, 0, out)
        self.assertIn("ios: version 1.0.1, build 18", out)
        self.assertIn("android: version 1.0.1, build 4", out)
        self.assertEqual(cli(p.root, "status")[0], versions.EXIT_DONE)
        self.assertEqual(cli(p.root, "set", "--version", "1.0.0")[0], versions.EXIT_ERROR, "never below the last release")

    def test_new_features_suggest_a_minor_bump_and_major_needs_the_owner(self):
        p = Project(self).capacitor(version="1.0.0")
        sha = p.commit()
        cli(p.root, "init")
        cli(p.root, "note", "--kind", "Added", "--text", "Launch", "--evidence", sha)
        p.write("receipt.json", "{}")
        cli(p.root, "release", "--evidence", "receipt.json")
        cli(p.root, "note", "--kind", "Added", "--text", "Daily puzzle", "--evidence", sha)
        self.assertIn("set --bump minor --next-build", cli(p.root, "status")[1])
        code, out = cli(p.root, "set", "--bump", "major")
        self.assertEqual(code, versions.EXIT_ERROR)
        self.assertIn("owner", out)
        self.assertEqual(cli(p.root, "set", "--bump", "major", "--owner-approved-major")[0], 0)

    def test_entries_without_evidence_or_with_missing_evidence_are_flagged(self):
        p = Project(self).capacitor(version="1.0.0")
        p.commit()
        cli(p.root, "init")
        log = p.root / "CHANGELOG.md"
        log.write_text(log.read_text() + "\n### Fixed\n- Hand-written entry\n- Another. Evidence: deadbeef1; missing/file.txt\n")
        code, out = cli(p.root, "status")
        self.assertEqual(code, versions.EXIT_NEXT)
        self.assertIn("has no `Evidence:`", out)
        self.assertIn("commit deadbeef1 is not in this repository", out)
        self.assertIn("missing/file.txt does not exist", out)

    def test_note_refuses_missing_evidence_and_duplicates(self):
        p = Project(self).capacitor(version="1.0.0")
        sha = p.commit()
        cli(p.root, "init")
        self.assertEqual(cli(p.root, "note", "--text", "Something")[0], versions.EXIT_ERROR)
        self.assertEqual(cli(p.root, "note", "--text", "Something", "--evidence", "nope.txt")[0], versions.EXIT_ERROR)
        self.assertEqual(cli(p.root, "note", "--text", "Something", "--evidence", "../outside.txt")[0], versions.EXIT_ERROR)
        cli(p.root, "note", "--text", "Something", "--evidence", sha)
        self.assertIn("already", cli(p.root, "note", "--text", "Something", "--evidence", sha)[1])

    def test_unity_set_updates_both_platform_builds(self):
        p = Project(self)
        p.write("ProjectSettings/ProjectSettings.asset", UNITY.format(version="1.0", ios=9, android=1))
        code, out = cli(p.root, "set", "--version", "1.0.0", "--next-build")
        self.assertEqual(code, 0, out)
        text = (p.root / "ProjectSettings/ProjectSettings.asset").read_text()
        self.assertIn("bundleVersion: 1.0.0", text)
        self.assertIn("    iPhone: 10\n    tvOS: 0", text)
        self.assertIn("AndroidBundleVersionCode: 2", text)
        self.assertIn("someOtherBlock:\n    iPhone: 1", text, "only the buildNumber block changes")

    def test_set_rejects_bad_versions_and_lower_builds(self):
        p = Project(self).capacitor(version="1.0.0")
        self.assertEqual(cli(p.root, "set", "--version", "1.0")[0], versions.EXIT_ERROR)
        self.assertEqual(cli(p.root, "set", "--version", "v1.0.0")[0], versions.EXIT_ERROR)
        self.assertEqual(cli(p.root, "set", "--build", "ios=5")[0], versions.EXIT_ERROR)

    def test_store_notes_drop_evidence_and_check_limits(self):
        p = Project(self).capacitor(version="1.0.0")
        sha = p.commit()
        cli(p.root, "init")
        cli(p.root, "note", "--kind", "Fixed", "--text", "Sound returns after a call", "--evidence", sha)
        cli(p.root, "note", "--kind", "Added", "--text", "Daily puzzle", "--evidence", sha)
        code, out = cli(p.root, "notes", "--version", "Unreleased", "--store", "google")
        self.assertEqual(code, 0)
        self.assertEqual(out.strip(), "• Daily puzzle.\n• Sound returns after a call.")
        cli(p.root, "note", "--kind", "Changed", "--text", "x" * 600, "--evidence", sha)
        self.assertEqual(cli(p.root, "notes", "--version", "Unreleased", "--store", "google")[0], versions.EXIT_ERROR)


if __name__ == "__main__":
    unittest.main()
