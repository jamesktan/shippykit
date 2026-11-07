"""Public asset history behavior, provenance boundaries and failure preservation."""

import base64
import copy
import hashlib
from html.parser import HTMLParser
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("asset_preview", ROOT / "docs/launch/harness/deploy/preview.py")
PREVIEW = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PREVIEW)
PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aZZkAAAAASUVORK5CYII=")
VIDEO = b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom" + bytes(range(64))


class Cards(HTMLParser):
    def __init__(self, page):
        super().__init__()
        self.cards = []
        self.current = None
        self.csp = None
        self.feed(page)

    def handle_starttag(self, tag, attributes):
        attrs = dict(attributes)
        if tag == "meta" and attrs.get("http-equiv") == "Content-Security-Policy":
            self.csp = attrs.get("content")
        if tag == "article" and "data-revision" in attrs:
            self.current = {"id": attrs["data-revision"], "text": [], "attributes": attrs}

    def handle_data(self, data):
        if self.current is not None:
            self.current["text"].append(data)

    def handle_endtag(self, tag):
        if tag == "article" and self.current is not None:
            self.current["text"] = " ".join(self.current["text"])
            self.cards.append(self.current)
            self.current = None


class AssetHistoryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.release = self.root / "release-output"
        self.release.mkdir()
        self.manifest = {"app": "Garden", "platform": "ios", "files": [],
                         "asset_history": {"schema_version": 1, "assets": []}}
        self.tree = self.add_asset("tree", "Garden tree")
        self.add_revision(self.tree, "r1", "2026-10-23T18:00:00Z", "Angular canopy")
        self.add_revision(self.tree, "r2", "2026-10-23T19:00:00Z", "Rounded canopy", parent="r1")
        self.tree.update(selected_revision="r2", integrated_revision="r1")

    def add_asset(self, identifier, label):
        asset = {"id": identifier, "label": label, "revisions": [], "events": []}
        self.manifest["asset_history"]["assets"].append(asset)
        return asset

    def add_revision(self, asset, identifier, date, direction, parent=None, extension=".png"):
        path = "artwork/review/" + asset["id"] + "/" + identifier + extension
        content = VIDEO if extension == ".mp4" else PNG
        self.file(path, "asset_revision_preview", content)
        row = {"id": identifier, "parent": parent, "direction": direction, "date": date,
               "reason": "Public design rationale for " + identifier, "preview_path": path}
        asset["revisions"].append(row)
        return row

    def file(self, path, kind, content):
        target = self.release / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        entry = {"path": path, "kind": kind, "sha256": hashlib.sha256(content).hexdigest(), "bytes": len(content)}
        self.manifest["files"].append(entry)
        return entry

    def build(self):
        (self.release / "manifest.json").write_text(json.dumps(self.manifest), encoding="utf-8")
        result = PREVIEW.build(self.release)
        site = Path(result["site"])
        return site, result, (site / "index.html").read_text()

    def test_grouping_and_selection_do_not_claim_new_candidate_is_integrated(self):
        rock = self.add_asset("rock", "River rock")
        self.add_revision(rock, "r1", "2026-10-22", "Weathered stone")
        _, result, page = self.build()
        self.assertEqual((result["asset_groups"], result["asset_revisions"]), (2, 3))
        self.assertIn('data-asset-id="tree"', page)
        self.assertIn('data-asset-id="rock"', page)
        self.assertLess(page.index("Asset revision history"), page.index("<h2>Icons</h2>"))
        cards = Cards(page).cards
        self.assertIn("Integrated", cards[0]["text"])
        self.assertNotIn("Selected", cards[0]["text"])
        self.assertIn("Selected", cards[1]["text"])
        self.assertNotIn("Integrated", cards[1]["text"])
        self.assertIn("Candidate", cards[2]["text"])
        self.assertIn("Integrated in app: <strong>r1</strong>", page)
        self.assertIn("Current selection: <strong>r2</strong>", page)
        self.assertIn(".revision-grid{display:grid;grid-template-columns:repeat(2", page)
        self.assertIn("@media(max-width:650px){.revision-grid{grid-template-columns:1fr", page)
        self.assertIn("does not change either state", page)
        self.assertNotIn("<button", page)  # No simulated selection/save controls.

    def test_same_revision_can_be_selected_and_integrated_and_null_is_honest(self):
        self.tree["selected_revision"] = "r1"
        _, _, page = self.build()
        first = Cards(page).cards[0]
        self.assertIn("Selected", first["text"])
        self.assertIn("Integrated", first["text"])
        self.tree.update(selected_revision=None, integrated_revision=None)
        _, _, page = self.build()
        self.assertIn("Current selection: <strong>Not recorded</strong>", page)
        self.assertIn("Integrated in app: <strong>Not recorded</strong>", page)
        self.assertNotIn("Not integrated", page)
        self.assertTrue(all("Candidate" in card["text"] for card in Cards(page).cards))

    def test_revisions_and_decision_events_are_chronological(self):
        self.tree["revisions"].reverse()
        self.tree["events"] = [
            {"id": "select", "type": "selection", "date": "2026-10-23T20:00:00Z", "revision_id": "r2", "reason": "Latest choice"},
            {"id": "direction", "type": "direction", "date": "2026-10-23T18:30:00Z", "direction": "Rounder", "reason": "New direction"},
            {"id": "integrate", "type": "integration", "date": "2026-10-23T18:10:00Z", "revision_id": "r1", "reason": "Earlier app integration"},
        ]
        _, _, page = self.build()
        self.assertEqual([card["id"] for card in Cards(page).cards], ["r1", "r2"])
        self.assertLess(page.index("Earlier app integration"), page.index("New direction"))
        self.assertLess(page.index("New direction"), page.index("Latest choice"))

    def test_private_journal_masters_prompts_and_unknown_fields_never_enter_site(self):
        private = "PRIVATE_PROMPT_OR_PROVENANCE"
        self.file("artwork/masters/tree/r1.png", "app_artwork", PNG + private.encode())
        self.file("artwork/revisions.json", "asset_revision_journal", json.dumps({"prompt": private}).encode())
        self.manifest["asset_history"]["private_journal"] = private
        self.tree["original_request"] = private
        self.tree["revisions"][0].update(prompt=private, original_path=private, provider_response={"raw": private})
        self.tree["events"] = [{"id": "decision", "type": "selection", "date": "2026-10-23T20:00:00Z", "revision_id": "r2", "reason": "Public choice", "private_reply": private}]
        site, _, page = self.build()
        for path in site.rglob("*"):
            if path.is_file():
                self.assertNotIn(private.encode(), path.read_bytes())
        for hidden in ("artwork/review", "artwork/masters", "revisions.json", "provider_response", str(self.release)):
            self.assertNotIn(hidden, page)
        registry = json.loads((site / PREVIEW.REGISTRY).read_text())
        self.assertTrue(all(path == "index.html" or path.startswith("assets/") for path in registry["files"]))

    def test_public_summaries_are_escaped_and_never_executable(self):
        payload = '<script>alert("x")</script><img src="https://example.invalid/pixel">'
        self.tree["label"] = '<img src=x onerror="alert(1)">'
        self.tree["revisions"][0].update(direction=payload, reason=payload)
        self.tree["events"] = [{"id": "e1", "type": "direction", "date": "2026-10-24", "direction": payload, "reason": payload}]
        _, _, page = self.build()
        self.assertNotIn('<script>alert(', page)
        self.assertNotIn('<img src=x', page)
        self.assertNotIn('<img src="https://', page)
        self.assertIn('&lt;script&gt;', page)
        self.assertIn("connect-src 'none'", Cards(page).csp)

    def test_rejection_then_reselection_updates_omitted_disposition_without_losing_events(self):
        self.add_revision(self.tree, "r3", "2026-10-24", "Wide canopy", parent="r2")
        self.tree["events"] = [{"id": "reject-r3", "type": "rejection", "date": "2026-10-24T12:00:00Z", "revision_id": "r3", "reason": "Too wide for the scene"}]
        _, _, page = self.build()
        third = Cards(page).cards[2]
        self.assertIn("Rejected", third["text"])
        self.assertNotIn("Candidate", third["text"])
        self.tree["selected_revision"] = "r3"
        with self.assertRaisesRegex(ValueError, "Selected revision"):
            self.build()
        self.tree["events"].append({"id": "select-r3", "type": "selection", "date": "2026-10-24T13:00:00Z", "revision_id": "r3", "reason": "Chosen after scene layout changed"})
        _, _, page = self.build()
        third = Cards(page).cards[2]
        self.assertIn("Selected", third["text"])
        self.assertNotIn("Rejected", third["text"])
        self.assertIn("Too wide for the scene", page)
        self.assertIn("Chosen after scene layout changed", page)

    def test_invalid_references_cycles_dates_and_duplicates_fail_without_replacing_site(self):
        site, _, _ = self.build()
        before = {p.name: p.read_bytes() for p in (site / "index.html", site / PREVIEW.REGISTRY)}
        baseline = copy.deepcopy(self.manifest)
        mutations = [
            lambda asset: asset.update(selected_revision="missing"),
            lambda asset: asset.update(integrated_revision="missing"),
            lambda asset: asset["revisions"][0].update(parent="missing"),
            lambda asset: asset["revisions"][0].update(parent="r1"),
            lambda asset: (asset["revisions"][0].update(parent="r2", date="2026-10-23"), asset["revisions"][1].update(date="2026-10-23")),
            lambda asset: asset["revisions"][0].update(date="2026-10-24"),
            lambda asset: asset["revisions"][0].update(date="2026-02-30"),
            lambda asset: asset["revisions"][0].update(date="not a date"),
            lambda asset: asset["revisions"][1].update(id="r1"),
            lambda asset: asset["revisions"][0].update(id='<img>'),
            lambda asset: asset["revisions"][1].update(preview_path=asset["revisions"][0]["preview_path"]),
            lambda asset: asset["revisions"][0].update(disposition={"private": "field"}),
            lambda asset: asset.update(events=[{"id": "e1", "type": "selection", "date": "2026-10-24", "reason": "Choose", "revision_id": "missing"}]),
            lambda asset: asset.update(events=[{"id": "e1", "type": "integration", "date": "2026-10-22", "reason": "Too early", "revision_id": "r1"}]),
            lambda asset: asset.update(events=[{"id": "e1", "type": "direction", "date": "2026-10-24", "reason": "Missing direction"}]),
            lambda asset: asset.update(events=[{"id": "e1", "type": [], "date": "2026-10-24", "reason": "Bad type"}]),
        ]
        for index, mutate in enumerate(mutations):
            with self.subTest(case=index):
                self.manifest = copy.deepcopy(baseline)
                mutate(self.manifest["asset_history"]["assets"][0])
                with self.assertRaises(ValueError):
                    self.build()
                self.assertEqual(before, {p.name: p.read_bytes() for p in (site / "index.html", site / PREVIEW.REGISTRY)})

    def test_missing_or_wrong_kind_preview_cannot_be_referenced(self):
        self.manifest["files"][0]["kind"] = "promo_image"
        with self.assertRaisesRegex(ValueError, "verified asset_revision_preview"):
            self.build()
        self.manifest["files"][0]["kind"] = "asset_revision_preview"
        (self.release / self.manifest["files"][0]["path"]).unlink()
        with self.assertRaises(ValueError):
            self.build()

    def test_history_and_public_file_references_are_complete_and_unambiguous(self):
        baseline = copy.deepcopy(self.manifest)
        self.manifest.pop("asset_history")
        with self.assertRaisesRegex(ValueError, "require asset_history"):
            self.build()
        self.manifest = copy.deepcopy(baseline)
        self.manifest["asset_history"]["assets"] = []
        with self.assertRaisesRegex(ValueError, "Unreferenced"):
            self.build()
        self.manifest = copy.deepcopy(baseline)
        self.manifest["files"].append(copy.deepcopy(self.manifest["files"][0]))
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            self.build()
        self.manifest = copy.deepcopy(baseline)
        self.manifest["asset_history"]["assets"].append(copy.deepcopy(self.tree))
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            self.build()

    def test_review_export_location_size_hash_and_symlink_boundaries(self):
        baseline = copy.deepcopy(self.manifest)
        for path in ("artwork/masters/tree/r1.png", "artwork/review/prompts/r1.png", "captures/r1.png", "../r1.png"):
            with self.subTest(path=path):
                self.manifest = copy.deepcopy(baseline)
                self.manifest["files"][0]["path"] = path
                with self.assertRaises(ValueError):
                    self.build()
        for field, value in (("bytes", None), ("bytes", True), ("bytes", 1), ("sha256", "0" * 64)):
            with self.subTest(field=field, value=value):
                self.manifest = copy.deepcopy(baseline)
                self.manifest["files"][0][field] = value
                with self.assertRaises(ValueError):
                    self.build()
        self.manifest = copy.deepcopy(baseline)
        path = self.release / self.manifest["files"][0]["path"]
        outside = self.root / "outside.png"
        outside.write_bytes(path.read_bytes())
        path.unlink()
        path.symlink_to(outside)
        with self.assertRaisesRegex(ValueError, "Symlinks"):
            self.build()

    def test_history_video_uses_real_controls_and_unrelated_outputs_survive_refresh(self):
        self.add_revision(self.tree, "r3", "2026-10-24", "Motion study", parent="r2", extension=".mp4")
        site, result, page = self.build()
        self.assertEqual(result["videos"], 1)
        self.assertIn('<video controls playsinline', page)
        self.assertIn('type="video/mp4"', page)
        (site / "owner-notes.txt").write_text("Preserve unrelated local output")
        self.tree["selected_revision"] = "r3"
        self.tree["integrated_revision"] = "r2"
        _, _, page = self.build()
        self.assertEqual((site / "owner-notes.txt").read_text(), "Preserve unrelated local output")
        self.assertIn("Integrated in app: <strong>r2</strong>", page)
        self.assertEqual(len(Cards(page).cards), 3)

    def test_legacy_manifest_without_history_keeps_existing_gallery(self):
        self.manifest = {"app": "Garden", "files": []}
        self.file("stores/ios/en-US/screen.png", "app_store_screenshot", PNG)
        _, result, page = self.build()
        self.assertEqual((result["asset_groups"], result["asset_revisions"]), (0, 0))
        self.assertIn("Screenshot 1", page)
        self.assertNotIn("<h2>Asset revision history</h2>", page)


if __name__ == "__main__":
    unittest.main()
