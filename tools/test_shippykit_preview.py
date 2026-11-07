"""Behavior/privacy checks for the portable, dependency-free release preview."""

import base64
import hashlib
import http.client
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "docs/launch/harness/deploy/preview.py"
SPEC = importlib.util.spec_from_file_location("shippykit_preview", SCRIPT)
PREVIEW = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PREVIEW)
PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aZZkAAAAASUVORK5CYII=")
VIDEO = b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom" + bytes(range(256))


class PreviewTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.release = self.root / "release-output"
        self.release.mkdir()
        self.manifest = {"schema_version": 1, "app": "Pocket Garden", "platform": "ios", "locale": "en-US",
                         "build": {"version": "1.2", "build": "6", "signing": "SIGNING_PRIVATE",
                                   "path": "builds/PRIVATE_ARCHIVE.xcarchive"}, "files": []}
        self.save_manifest()

    def save_manifest(self):
        (self.release / "manifest.json").write_text(json.dumps(self.manifest), encoding="utf-8")

    def asset(self, path, kind, content=PNG, **extra):
        destination = self.release / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)
        entry = {"path": path, "kind": kind, "sha256": hashlib.sha256(content).hexdigest(), "bytes": len(content), **extra}
        self.manifest["files"].append(entry)
        return entry

    def build(self, output=None):
        self.save_manifest()
        result = PREVIEW.build(self.release, output)
        site = Path(result["site"])
        return site, result, (site / "index.html").read_text(encoding="utf-8")

    def all_public_text(self, site):
        return "\n".join(path.read_text(encoding="utf-8") for path in site.rglob("*")
                         if path.is_file() and path.suffix in {".html", ".txt", ".json"})

    def start_server(self, site):
        server = PREVIEW.make_server(site, 0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        def cleanup():
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)
        self.addCleanup(cleanup)
        self.assertEqual(server.server_address[0], "127.0.0.1")
        return server.server_port

    def request(self, port, path, method="GET", headers=None):
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
        try:
            connection.request(method, path, headers=headers or {})
            response = connection.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            connection.close()

    def test_real_listing_has_only_public_sections_and_never_source_paths(self):
        self.asset("stores/ios/en-US/iphone-6.3/SECRET_INTERNAL_filename.png", "app_store_screenshot")
        self.asset("stores/ios/en-US/app-preview.mp4", "app_store_preview", VIDEO)
        self.asset("stores/ios/en-US/listing.md", "store_copy", """# Pocket Garden — App Store copy

Bundle ID: PRIVATE_BUNDLE

## Name
Pocket Garden
## Subtitle
A space to grow
## Description
Plant a small garden.
### Private implementation notes
PRIVATE_IMPLEMENTATION
#### Description
PRIVATE_NESTED_KNOWN_HEADING
## Keywords
garden,offline
## What's new in version 1.2
New flowers.
## Review notes
PRIVATE_REVIEW_PASSWORD
### Title
PRIVATE_REVIEW_CHILD
## Unresolved store fields
PRIVATE_OWNER_CONTACT
""".encode("utf-8"))
        self.asset("logs/log.txt", "build_log", b"PRIVATE_LOG")
        self.asset("captures/raw.png", "raw_screenshot")
        self.asset("builds/embedded.mobileprovision", "build_file", b"PRIVATE_PROFILE")
        site, result, page = self.build()
        self.assertEqual((result["images"], result["videos"], result["public_listings"]), (1, 1, 1))
        public = self.all_public_text(site)
        self.assertNotIn("PRIVATE", public)
        self.assertNotIn("SECRET_INTERNAL", public)
        self.assertNotIn("stores/ios", public)
        self.assertIn("Plant a small garden.", page)
        self.assertIn("New flowers.", page)
        self.assertIn("Version 1.2", page)
        self.assertIn("Build 6", page)
        self.assertIn("<video controls", page)
        self.assertEqual(len(list((site / "assets").glob("*.txt"))), 1)
        self.assertFalse(list(site.rglob("*.md")))
        registry = PREVIEW.owned_registry(site)
        self.assertEqual(len(registry["files"]), 4)

    def test_unknown_sections_and_setext_headings_do_not_leak_nested_public_names(self):
        text = """Store copy
==========
Description
-----------
PUBLIC_DESCRIPTION
### Notes
PRIVATE_NESTED
#### Name
PRIVATE_NAME
Review notes
------------
PRIVATE_REVIEW
### Description
PRIVATE_DESCENDANT
Release notes
-------------
PUBLIC_RELEASE
"""
        sections = PREVIEW.store_sections(text, "App")
        self.assertEqual(sections, [("Description", "PUBLIC_DESCRIPTION"), ("Release notes", "PUBLIC_RELEASE")])
        self.assertEqual(PREVIEW.store_sections("# Review notes\n## Description\nPRIVATE", "App"), [])

    def test_code_fences_cannot_turn_private_text_into_a_public_heading(self):
        text = "## Review notes\n```markdown\n## Description\nPRIVATE\n```\n## Name\nPublic app"
        self.assertEqual(PREVIEW.store_sections(text, "App"), [("Name", "Public app")])

    def test_html_is_literal_in_page_and_public_text_download(self):
        self.manifest["app"] = '<img src="https://evil.invalid/pixel" onerror="alert(1)">'
        dangerous = '<script>alert("COPY_PRIVATE_EXECUTION")</script>\n![track](https://evil.invalid/pixel)'
        self.asset("stores/ios/listing.md", "store_copy", ("## Description\n" + dangerous).encode())
        site, _, page = self.build()
        self.assertNotIn('<img src="https://', page)
        self.assertNotIn('<script>alert(', page)
        self.assertIn("&lt;script&gt;", page)
        copy = next((site / "assets").glob("*.txt")).read_text()
        self.assertIn(dangerous, copy)
        port = self.start_server(site)
        status, headers, _ = self.request(port, "/assets/" + next((site / "assets").glob("*.txt")).name)
        self.assertEqual(status, 200)
        self.assertEqual(headers["Content-Type"], "text/plain; charset=utf-8")
        self.assertEqual(headers["X-Content-Type-Options"], "nosniff")
        self.assertIn("connect-src 'none'", headers["Content-Security-Policy"])

    def test_explicit_preview_copy_can_be_authored_without_store_headings(self):
        self.asset("public/welcome.txt", "preview_copy", b"An explicitly public introduction.\nNo account required.")
        _, result, page = self.build()
        self.assertEqual(result["public_listings"], 1)
        self.assertIn("An explicitly public introduction.", page)

    def test_empty_or_private_only_manifest_has_honest_empty_sections(self):
        self.manifest["files"].append({"kind": "build_file", "path": "../../must-not-read"})
        self.asset("stores/ios/listing.md", "store_copy", b"## Review notes\nPRIVATE_ONLY")
        site, result, page = self.build()
        self.assertEqual((result["images"], result["videos"], result["public_listings"]), (0, 0, 0))
        self.assertIn("No icons are included", page)
        self.assertIn("No public listing sections", page)
        self.assertNotIn("PRIVATE_ONLY", self.all_public_text(site))

    def test_uploaded_originals_stay_private_while_prepared_marketing_is_viewable(self):
        original = self.asset("inputs/photo/original.png", "user_media", PNG)
        self.asset("inputs/clip/original.mp4", "user_media", VIDEO)
        self.asset("inputs/index.json", "user_media_index", b'{"original_filename":"PRIVATE_USER_FILENAME","role":"edit_target"}')
        self.asset("promo/campaign.png", "promo_image", PNG)
        self.asset("promo/campaign.mp4", "promo_video", VIDEO)
        site, result, page = self.build()
        self.assertEqual((result["images"], result["videos"]), (1, 1))
        self.assertNotIn("PRIVATE_USER_FILENAME", self.all_public_text(site))
        self.assertNotIn("inputs/", page)
        self.assertEqual((self.release / original["path"]).read_bytes(), PNG)
        port = self.start_server(site)
        for raw in ("inputs/index.json", "inputs/photo/original.png", "inputs/clip/original.mp4"):
            self.assertEqual(self.request(port, "/" + raw)[0], 404)
        before = (site / "index.html").read_bytes()
        original["kind"] = "promo_image"
        with self.assertRaisesRegex(ValueError, "Private source locations"):
            self.build()
        self.assertEqual((site / "index.html").read_bytes(), before)

    def test_multiplatform_icons_and_missing_platform_labels_are_explicit(self):
        self.manifest.pop("platform")
        self.asset("stores/ios/en-US/icon.png", "app_icon")
        self.asset("stores/android/fr-FR/icon.webp", "launcher_icon", b"RIFF\x20\x00\x00\x00WEBPVP8 " + bytes(20))
        self.asset("public/icon.jpg", "store_icon", b"\xff\xd8\xff\xe0" + bytes(20))
        _, result, page = self.build()
        self.assertEqual(result["images"], 3)
        for label in ("iOS", "Android", "fr-FR", "Unspecified platform", 'data-filter="all"', 'class="grid icons"'):
            self.assertIn(label, page)

    def test_private_documents_cannot_be_relabelled_as_public_copy(self):
        for name in ("README.md", "STATE.md", "APP.md", "needs-input.md"):
            with self.subTest(name=name):
                self.manifest["files"] = []
                self.asset(name, "preview_copy", b"## Description\nPRIVATE_CONFIGURATION")
                with self.assertRaisesRegex(ValueError, "Private source"):
                    self.build()

    def test_missing_hash_hash_mismatch_size_mismatch_and_invalid_format_fail_closed(self):
        entry = self.asset("stores/ios/screen.png", "app_store_screenshot")
        original = dict(entry)
        cases = [("sha256", None), ("sha256", "0" * 64), ("bytes", 1)]
        for field, value in cases:
            with self.subTest(field=field, value=value):
                entry.clear()
                entry.update(original)
                entry[field] = value
                with self.assertRaises(ValueError):
                    self.build()
                self.assertFalse((self.release / "site").exists())
        entry.clear()
        entry.update(original)
        bad = b"<html>not an image</html>"
        (self.release / entry["path"]).write_bytes(bad)
        entry.update(sha256=hashlib.sha256(bad).hexdigest(), bytes=len(bad))
        with self.assertRaisesRegex(ValueError, "format"):
            self.build()

    def test_traversal_absolute_windows_paths_and_private_locations_are_rejected(self):
        for path in ("../outside.png", "/tmp/outside.png", "stores/../../outside.png", "stores//screen.png",
                     "C:\\private\\screen.png", "captures/raw.png", "logs/screenshot.png", ".secrets/icon.png"):
            with self.subTest(path=path):
                self.manifest["files"] = [{"kind": "app_store_screenshot", "path": path, "sha256": "a" * 64}]
                with self.assertRaises(ValueError):
                    self.build()

    def test_file_directory_manifest_and_root_symlinks_are_rejected(self):
        outside = self.root / "outside.png"
        outside.write_bytes(PNG)
        public = self.release / "public"
        public.mkdir()
        (public / "linked.png").symlink_to(outside)
        self.manifest["files"] = [{"kind": "app_icon", "path": "public/linked.png", "sha256": hashlib.sha256(PNG).hexdigest()}]
        with self.assertRaises(ValueError):
            self.build()
        (self.release / "linked-dir").symlink_to(public, target_is_directory=True)
        self.manifest["files"][0]["path"] = "linked-dir/linked.png"
        with self.assertRaises(ValueError):
            self.build()
        self.manifest["files"] = []
        self.save_manifest()
        backup = self.root / "manifest.json"
        (self.release / "manifest.json").rename(backup)
        (self.release / "manifest.json").symlink_to(backup)
        with self.assertRaises(ValueError):
            PREVIEW.build(self.release)
        link = self.root / "release-link"
        link.symlink_to(self.release, target_is_directory=True)
        with self.assertRaises(ValueError):
            PREVIEW.build(link)

    def test_nonowned_output_and_user_modified_generated_files_are_preserved(self):
        unowned = self.root / "my-site"
        unowned.mkdir()
        (unowned / "index.html").write_text("UNRELATED")
        with self.assertRaisesRegex(ValueError, "not owned"):
            self.build(unowned)
        self.assertEqual((unowned / "index.html").read_text(), "UNRELATED")
        site, _, _ = self.build()
        (site / "index.html").write_text("USER_EDIT")
        with self.assertRaisesRegex(ValueError, "changed"):
            self.build()
        self.assertEqual((site / "index.html").read_text(), "USER_EDIT")

    def test_refresh_removes_only_old_generated_assets_and_preserves_unrelated_files(self):
        self.asset("stores/ios/screen.png", "app_store_screenshot")
        site, _, _ = self.build()
        old_asset = next((site / "assets").glob("*.png"))
        (site / "notes.txt").write_text("PRIVATE_LEFTOVER")
        (site / "assets/unrelated.png").write_bytes(b"UNRELATED")
        self.manifest["files"] = []
        self.build()
        self.assertFalse(old_asset.exists())
        self.assertEqual((site / "notes.txt").read_text(), "PRIVATE_LEFTOVER")
        self.assertEqual((site / "assets/unrelated.png").read_bytes(), b"UNRELATED")
        port = self.start_server(site)
        for path in ("/notes.txt", "/assets/unrelated.png", "/assets/", "/" + PREVIEW.REGISTRY):
            self.assertEqual(self.request(port, path)[0], 404, path)

    def test_failed_refresh_keeps_previous_public_page_and_registry(self):
        self.asset("stores/ios/screen.png", "app_store_screenshot")
        site, _, page = self.build()
        before = (site / PREVIEW.REGISTRY).read_bytes()
        self.asset("stores/ios/missing.png", "app_icon")
        (self.release / "stores/ios/missing.png").unlink()
        with self.assertRaises(ValueError):
            self.build()
        self.assertEqual((site / "index.html").read_text(), page)
        self.assertEqual((site / PREVIEW.REGISTRY).read_bytes(), before)

    def test_server_denies_unlisted_traversal_symlink_and_changed_files(self):
        self.asset("stores/ios/screen.png", "app_store_screenshot")
        site, _, _ = self.build()
        port = self.start_server(site)
        for path in ("/../manifest.json", "/%2e%2e/manifest.json", "/assets/../index.html",
                     "/%2fetc/passwd", "/%252e%252e/manifest.json", "/assets%5c..%5cmanifest.json"):
            self.assertEqual(self.request(port, path)[0], 404, path)
        public = next((site / "assets").glob("*.png"))
        url = "/assets/" + public.name
        public.write_bytes(b"PRIVATE_REPLACEMENT")
        self.assertEqual(self.request(port, url)[0], 404)
        public.unlink()
        source = self.release / "stores/ios/screen.png"
        public.symlink_to(source)
        self.assertEqual(self.request(port, url)[0], 404)
        with self.assertRaises(ValueError):
            PREVIEW.make_server(site, 0)

    def test_video_ranges_suffix_open_ended_and_head(self):
        self.asset("stores/ios/preview.mp4", "app_store_preview", VIDEO)
        site, _, _ = self.build()
        port = self.start_server(site)
        path = "/assets/" + next((site / "assets").glob("*.mp4")).name
        for header, expected in (("bytes=0-15", VIDEO[:16]), ("bytes=-12", VIDEO[-12:]),
                                 ("bytes=250-", VIDEO[250:]), ("bytes=0-9999", VIDEO)):
            with self.subTest(header=header):
                code, headers, body = self.request(port, path, headers={"Range": header})
                self.assertEqual(code, 206)
                self.assertEqual(body, expected)
                self.assertEqual(int(headers["Content-Length"]), len(expected))
                self.assertTrue(headers["Content-Range"].endswith("/" + str(len(VIDEO))))
        for invalid in ("bytes=9999-", "bytes=5-1", "bytes=0-1,3-5", "bytes=-0", "bytes=-", "nonsense"):
            self.assertEqual(self.request(port, path, headers={"Range": invalid})[0], 416)
        code, headers, body = self.request(port, path, "HEAD")
        self.assertEqual((code, len(body), int(headers["Content-Length"])), (200, 0, len(VIDEO)))
        code, _, body = self.request(port, path, headers={"Range": "bytes=0-1", "If-Range": '"outdated"'})
        self.assertEqual((code, body), (200, VIDEO))

    def test_abandoned_video_response_does_not_send_a_second_status(self):
        self.asset("stores/ios/preview.mp4", "app_store_preview", VIDEO)
        site, _, _ = self.build()
        server = PREVIEW.make_server(site, 0)
        self.addCleanup(server.server_close)
        path = "/assets/" + next((site / "assets").glob("*.mp4")).name
        for disconnect in (BrokenPipeError, ConnectionResetError):
            with self.subTest(disconnect=disconnect.__name__):
                # Exercise the real response path with a deterministic cancelled
                # socket, avoiding timing-dependent TCP-reset tests.
                class AbandonedSocket:
                    def write(self, _data):
                        raise disconnect("Browser cancelled video request")

                handler = object.__new__(server.RequestHandlerClass)
                handler.path = path
                handler.headers = {"Range": "bytes=0-15"}
                handler.wfile = AbandonedSocket()
                responses = []
                handler.send_response = responses.append
                handler.send_header = lambda *_args: None
                handler.end_headers = lambda: None
                handler.deliver(False)
                self.assertEqual(responses, [206])

    def test_generated_page_is_self_contained_and_cli_builds_outside_release_directory(self):
        self.asset("stores/ios/screen.png", "app_store_screenshot")
        self.save_manifest()
        output = self.root / "review-site"
        process = subprocess.run([sys.executable, str(SCRIPT), "build", "--release-output", str(self.release),
                                  "--output", str(output)], capture_output=True, text=True, check=True)
        self.assertIn("file://", process.stdout)
        page = (output / "index.html").read_text()
        for unwanted in ("https://", "http://", "fetch(", "XMLHttpRequest", str(self.release)):
            self.assertNotIn(unwanted, page)
        self.assertIn('<meta name="viewport"', page)
        self.assertIn("assets/", page)


if __name__ == "__main__":
    unittest.main()
