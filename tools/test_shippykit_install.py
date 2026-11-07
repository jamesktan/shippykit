"""Exercise real local install/upgrade behavior in isolated project fixtures."""

import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "docs/launch/harness/install.py"
SPEC = importlib.util.spec_from_file_location("shippykit_install", SCRIPT)
INSTALLER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(INSTALLER)


class InstallTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="shippykit install ")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.package = self.root / "package"
        self.project = self.root / "Existing app with spaces"
        self.package.mkdir()
        self.project.mkdir()
        self.source("VERSION", "0.1.0\n")
        self.source("deploy/README.md", "# Local deployment workflow v1\n")
        self.source("deploy/RESUME.md", "# Resume from durable app memory\n")
        self.source("deploy/APP.md", "# App template\n")
        self.source("deploy/STATE.md", "# State template\n")
        self.source("deploy/shippykit.py", "raise SystemExit('installer must not run this')\n")
        for name in ("shippykit", "shippykit-images", "shippykit-store-copy"):
            self.source("skills/" + name + "/SKILL.md", "---\nname: " + name + "\n---\n# Instructions\n")
            self.source("skills/" + name + "/agents/openai.yaml", "interface:\n  display_name: " + name + "\n")

    def source(self, name, content):
        path = self.package / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def local(self, name, content):
        path = self.project / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content if isinstance(content, bytes) else content.encode("utf-8"))
        return path

    def install(self, **options):
        return INSTALLER.install(self.package, self.project, **options)

    def receipt(self):
        return json.loads((self.project / ".shippykit/install.json").read_text())

    def snapshot(self):
        return {p.relative_to(self.project).as_posix(): (p.read_bytes(), p.stat().st_mtime_ns)
                for p in self.project.rglob("*") if p.is_file()}

    def test_fresh_both_agent_discovery_and_portable_receipt(self):
        result = self.install()
        self.assertFalse(result["conflicts"])
        for location in (".agents/skills", ".claude/skills"):
            for skill in ("shippykit", "shippykit-images", "shippykit-store-copy"):
                self.assertTrue((self.project / location / skill / "SKILL.md").is_file())
                self.assertTrue((self.project / location / skill / "agents/openai.yaml").is_file())
        for name in ("AGENTS.md", "CLAUDE.md"):
            text = (self.project / name).read_text()
            for link in ("deploy/README.md", "deploy/RESUME.md", "deploy/APP.md", "deploy/STATE.md"):
                self.assertIn(link, text)
        receipt = self.receipt()
        self.assertEqual(receipt["package_version"], "0.1.0")
        self.assertNotIn(str(self.root), json.dumps(receipt))
        self.assertEqual(result["next"], "Resume ShippyKit")
        self.assertFalse((self.project / ".shippykit/discovery.json").exists())

    def test_repeat_does_not_change_bytes_mtimes_or_duplicate_blocks(self):
        self.install()
        before = self.snapshot()
        result = self.install()
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(result["installed"], [])
        self.assertEqual(result["updated"], [])
        for name in ("AGENTS.md", "CLAUDE.md"):
            self.assertEqual((self.project / name).read_text().count("<!-- shippykit:begin -->"), 1)

    def test_existing_app_state_instructions_and_custom_files_survive(self):
        memory = {"deploy/APP.md": b"Existing app and identity\r\n",
                  "deploy/STATE.md": b"Previously uploaded build 17; pending owner reply\n",
                  "deploy/custom-operation.txt": b"Keep this custom command\n"}
        for name, content in memory.items():
            self.local(name, content)
        prefix = b"# Local rules\nNever remove these instructions.\n"
        for name in ("AGENTS.md", "CLAUDE.md"):
            self.local(name, prefix)
        self.local(".gitignore", "/existing-private/\n")
        self.install()
        for name, content in memory.items():
            self.assertEqual((self.project / name).read_bytes(), content)
        for name in ("AGENTS.md", "CLAUDE.md"):
            self.assertTrue((self.project / name).read_bytes().startswith(prefix))
        ignores = (self.project / ".gitignore").read_text()
        self.assertTrue(ignores.startswith("/existing-private/\n"))
        self.assertIn("/.shippykit/incoming/", ignores)
        self.assertIn("/.shippykit/discovery.json", ignores)
        self.assertNotIn("install.json", ignores)

    def test_safe_upgrade_changes_managed_files_but_never_memory(self):
        self.install()
        original_app = (self.project / "deploy/APP.md").read_bytes()
        self.local("deploy/STATE.md", "Owner answered no; continue only iOS.\n")
        self.source("VERSION", "0.2.0\n")
        self.source("deploy/README.md", "# Updated workflow\n")
        self.source("deploy/APP.md", "# New app template, must not replace memory\n")
        self.source("deploy/STATE.md", "# New state template\n")
        result = self.install()
        self.assertIn("deploy/README.md", result["updated"])
        self.assertEqual((self.project / "deploy/README.md").read_text(), "# Updated workflow\n")
        self.assertEqual((self.project / "deploy/APP.md").read_bytes(), original_app)
        self.assertEqual((self.project / "deploy/STATE.md").read_text(), "Owner answered no; continue only iOS.\n")
        self.assertEqual(self.receipt()["package_version"], "0.2.0")

    def test_edited_managed_and_unknown_files_are_not_adopted(self):
        self.local("deploy/README.md", "Local customized deployment procedure\n")
        first = self.install()
        self.assertEqual(len(first["conflicts"]), 1)
        self.assertNotIn("deploy/README.md", self.receipt()["managed_files"])
        self.assertEqual((self.project / ".shippykit/incoming/deploy/README.md").read_bytes(),
                         (self.package / "deploy/README.md").read_bytes())
        old_owned = self.receipt()["managed_files"]["deploy/RESUME.md"]
        self.local("deploy/RESUME.md", "Custom resume sequence\n")
        self.source("deploy/RESUME.md", "Upstream resume update\n")
        self.install()
        self.assertEqual(self.receipt()["managed_files"]["deploy/RESUME.md"], old_owned)
        self.assertEqual((self.project / "deploy/RESUME.md").read_text(), "Custom resume sequence\n")
        before = self.snapshot()
        self.install()
        self.assertEqual(self.snapshot(), before)

    def test_accepting_incoming_file_resolves_conflict_and_enables_future_upgrade(self):
        self.local("deploy/README.md", "Custom\n")
        self.install()
        shutil.copyfile(self.project / ".shippykit/incoming/deploy/README.md", self.project / "deploy/README.md")
        self.assertFalse(self.install()["conflicts"])
        self.source("deploy/README.md", "Next official version\n")
        self.assertIn("deploy/README.md", self.install()["updated"])

    def test_modified_incoming_candidate_is_preserved(self):
        self.local("deploy/README.md", "Custom\n")
        self.install()
        candidate = self.local(".shippykit/incoming/deploy/README.md", "Owner merge notes\n")
        self.source("deploy/README.md", "Upstream v2\n")
        result = self.install()
        self.assertEqual(candidate.read_text(), "Owner merge notes\n")
        self.assertIn(".upstream-", result["conflicts"][0]["incoming"])
        before = self.snapshot()
        self.install()
        self.assertEqual(self.snapshot(), before)

    def test_instruction_edit_is_preserved_without_duplicate_pointer(self):
        self.install()
        p = self.project / "AGENTS.md"
        p.write_text(p.read_text().replace("Start with", "Owner policy: start with") + "\nOther new rules\n")
        result = self.install()
        self.assertEqual(p.read_text().count("<!-- shippykit:begin -->"), 1)
        self.assertIn("Owner policy", p.read_text())
        self.assertIn("Other new rules", p.read_text())
        self.assertTrue(any(c["path"] == "AGENTS.md" for c in result["conflicts"]))

    def test_unrelated_instruction_edits_do_not_create_conflict(self):
        self.install()
        p = self.project / "CLAUDE.md"
        p.write_text("# Team rules\n\n" + p.read_text() + "\nTail preserved\n")
        self.assertFalse(self.install()["conflicts"])
        self.assertTrue(p.read_text().startswith("# Team rules"))
        self.assertTrue(p.read_text().endswith("Tail preserved\n"))

    def test_dry_run_including_conflict_does_not_mutate(self):
        self.local("deploy/README.md", "Customized\n")
        before = self.snapshot()
        result = self.install(dry_run=True)
        self.assertTrue(result["conflicts"])
        self.assertEqual(self.snapshot(), before)
        missing = self.root / "new app"
        INSTALLER.install(self.package, missing, dry_run=True)
        self.assertFalse(missing.exists())

    def test_source_symlink_refused_before_any_write(self):
        outside = self.root / "secret"
        outside.write_text("must not be copied")
        (self.package / "deploy/linked.md").symlink_to(outside)
        with self.assertRaises(INSTALLER.InstallError):
            self.install()
        self.assertEqual(list(self.project.iterdir()), [])

    def test_destination_directory_escape_refused_before_any_write(self):
        outside = self.root / "outside"
        outside.mkdir()
        (self.project / ".agents").symlink_to(outside, target_is_directory=True)
        with self.assertRaises(INSTALLER.InstallError):
            self.install()
        self.assertEqual(list(outside.iterdir()), [])
        self.assertFalse((self.project / "deploy").exists())

    def test_destination_file_symlink_and_project_symlink_refused(self):
        outside = self.root / "owner.txt"
        outside.write_text("untouched")
        (self.project / "deploy").mkdir()
        (self.project / "deploy/README.md").symlink_to(outside)
        with self.assertRaises(INSTALLER.InstallError):
            self.install()
        self.assertEqual(outside.read_text(), "untouched")
        link = self.root / "project-link"
        link.symlink_to(self.project, target_is_directory=True)
        with self.assertRaises(INSTALLER.InstallError):
            INSTALLER.install(self.package, link)

    def test_receipt_path_escape_and_root_overlap_refused(self):
        self.local(".shippykit/install.json", json.dumps({"schema_version": 1, "managed_files": {"../outside": "0" * 64}}))
        before = self.snapshot()
        with self.assertRaises(INSTALLER.InstallError):
            self.install()
        self.assertEqual(self.snapshot(), before)
        for target in (Path("/"), Path.home(), self.package, self.package / "inside", self.root):
            with self.subTest(target=target), self.assertRaises(INSTALLER.InstallError):
                INSTALLER.install(self.package, target, dry_run=True)

    def test_portable_receipt_rejects_drive_or_nul_paths(self):
        for path in ("C:/outside", "deploy/file:stream", "deploy/file\0.md"):
            with self.subTest(path=path):
                self.local(".shippykit/install.json", json.dumps({"schema_version": 1, "managed_files": {path: "0" * 64}}))
                before = self.snapshot()
                with self.assertRaises(INSTALLER.InstallError):
                    self.install()
                self.assertEqual(self.snapshot(), before)

    def test_package_license_is_installed_with_deploy_files(self):
        self.source("LICENSE", "MIT License\n\nCopyright (c) 2026 James Tan\n")
        result = self.install()
        self.assertIn("deploy/LICENSE", result["installed"])
        self.assertEqual((self.project / "deploy/LICENSE").read_text(), "MIT License\n\nCopyright (c) 2026 James Tan\n")
        self.assertIn("deploy/LICENSE", self.receipt()["managed_files"])
        self.assertFalse((self.project / "LICENSE").exists())

    def test_incomplete_package_cannot_install_broken_resume_or_skill_links(self):
        for name in ("deploy/RESUME.md", "deploy/shippykit.py", "skills/shippykit/SKILL.md"):
            with self.subTest(name=name):
                path = self.package / name
                content = path.read_bytes()
                path.unlink()
                with self.assertRaises(INSTALLER.InstallError):
                    self.install()
                self.assertEqual(list(self.project.iterdir()), [])
                path.write_bytes(content)

    def test_skip_junk_and_unrelated_source_but_refuse_sensitive_artifacts(self):
        self.source("deploy/__pycache__/cache.pyc", "junk")
        self.source("deploy/.DS_Store", "junk")
        self.source("skills/.private-note", "junk")
        self.source("unrelated-root-data.json", "never install this")
        self.install()
        self.assertFalse((self.project / "deploy/__pycache__").exists())
        self.assertFalse((self.project / "deploy/.DS_Store").exists())
        self.assertFalse((self.project / "unrelated-root-data.json").exists())
        self.source("deploy/signing.p8", "private artifact")
        before = self.snapshot()
        with self.assertRaises(INSTALLER.InstallError):
            self.install()
        self.assertEqual(self.snapshot(), before)

    def test_selected_agent_only_then_both_keeps_prior_discovery(self):
        self.install(agent="codex")
        self.assertFalse((self.project / ".claude").exists())
        self.assertFalse((self.project / "CLAUDE.md").exists())
        self.install(agent="claude")
        self.assertTrue((self.project / ".agents/skills/shippykit/SKILL.md").exists())
        self.assertTrue((self.project / ".claude/skills/shippykit/SKILL.md").exists())
        self.assertEqual(self.receipt()["installed_agents"], ["claude", "codex"])

    def test_single_agent_refresh_retains_other_agents_unresolved_conflicts(self):
        self.install()
        name = ".claude/skills/shippykit/SKILL.md"
        self.local(name, "Owner-customized Claude instructions\n")
        self.install()
        existing = next(c for c in self.receipt()["conflicts"] if c["path"] == name)
        result = self.install(agent="codex")
        self.assertIn(existing, result["conflicts"])
        self.assertIn(existing, self.receipt()["conflicts"])
        self.assertEqual((self.project / name).read_text(), "Owner-customized Claude instructions\n")

    def test_setup_wrapper_default_cwd_and_cli_dry_run(self):
        checkout = self.root / "ShippyKit checkout"
        destination = checkout / "docs/launch/harness"
        shutil.copytree(self.package, destination)
        shutil.copyfile(SCRIPT, destination / "install.py")
        shutil.copyfile(ROOT / "setup", checkout / "setup")
        (checkout / "setup").chmod(0o755)
        dry = subprocess.run([sys.executable, str(destination / "install.py"), str(self.project), "--dry-run"],
                             capture_output=True, text=True, timeout=10)
        self.assertEqual(dry.returncode, 0, dry.stderr)
        self.assertEqual(list(self.project.iterdir()), [])
        actual = subprocess.run([str(checkout / "setup"), "--agent", "claude"], cwd=self.project,
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(actual.returncode, 0, actual.stderr)
        self.assertIn("Next: Resume ShippyKit", actual.stdout)
        self.assertTrue((self.project / ".claude/skills/shippykit/SKILL.md").is_file())
        self.assertFalse((self.project / ".agents").exists())


if __name__ == "__main__":
    unittest.main()
