# Preserve and review asset revisions

Use this for new or revised in-game artwork, icons and other generated assets.
Follow the requested scope and the applicable image skill. Changing direction
creates a new revision; it does not erase the previous generation or imply that
the selected candidate has been integrated into the app. Resume from existing
[APP.md](APP.md), [STATE.md](STATE.md) and [RESUME.md](RESUME.md).

## Keep durable private history

Maintain `release-output/artwork/revisions.json` as an internal journal. Use
stable asset IDs (for example `garden-tree`) and revision IDs (`r1`, `r2`). Keep
the journal out of the public preview, public manifest entries and shared
reports; use secure references for sensitive prompts, inputs and decisions.

- Save each original generation under a distinct immutable path such as
  `artwork/masters/garden-tree/r1/tree.png`. Retain its SHA-256, byte size,
  generation/provenance evidence and applicable source references. Never reuse
  that path for a later result, even when a candidate is rejected.
- For each revision record `id`, `parent` (another revision or null), `direction`,
  `date`, `reason`, original file identity and any review export path. Parentage
  belongs to the same asset. Preserve every branch and rejected candidate.
- Keep `selected_revision` and `integrated_revision` separately. Selection is a
  design decision. Update integration only after the actual app asset/reference
  change and relevant validation; record the affected target/source revision and
  evidence privately. A selection alone must not update integration.
- Append events with stable `id`, `type` (`direction`, `selection`, `integration`
  or `rejection`), `date`, `reason`, and the relevant `revision_id` or `direction`.
  A new direction adds an event and subsequent revision, preserving earlier
  decisions. Correct a decision with a new event rather than rewriting history.
- Link this journal and the current selection/integration evidence from STATE.
  Preserve it on installation, regeneration and resume. Store raw prompt/input
  details privately; never use the complete journal as a public listing file.

The journal can use the public structure below plus private provenance fields.
It is maintained by the agent; the preview builder neither reads nor modifies
it. Write journal updates atomically after retaining the original files. Do not
invent missing historical reasons or dates; investigate or keep the uncertainty
private until a truthful public summary is available.

For existing artwork with no generation history, preserve its actual bytes and
create a baseline record dated when it was observed today. State that the
original generation date, prompt or provider is unknown rather than inventing
those details. A revision's `date` is its record date; an observed legacy
baseline is not evidence that the artwork was generated on that date.

## Export an explicit public review subset

Prepare sanitized image/video review exports under
`release-output/artwork/review/<asset-id>/<revision-id>.<ext>`. Retain distinct
source paths for every revision. Inspect them for private material, unwanted
metadata and truthful appearance before allowing them into the gallery. These
are review exports, not new originals; keep the masters and exact provenance.

Add only inspected review exports to `manifest.json`'s existing `files` array:

```json
{
  "kind": "asset_revision_preview",
  "path": "artwork/review/garden-tree/r2.png",
  "sha256": "<actual SHA-256 of this export>",
  "bytes": 12345,
  "platform": "ios"
}
```

The SHA-256 and positive byte size must match the actual file. Supported formats
are the preview builder's existing PNG/JPEG/WebP and video formats. No raw
`app_artwork` entry, master, prompt or journal is public by default. The new kind
requires an `artwork/review/` path and a corresponding revision below; a file
tagged as some other kind cannot satisfy that reference.

Add this optional top-level **public-only** `asset_history` object. The example
assumes both r1/r2 exports have matching `asset_revision_preview` entries:

```json
{
  "asset_history": {
    "schema_version": 1,
    "assets": [{
      "id": "garden-tree",
      "label": "Garden tree",
      "selected_revision": "r2",
      "integrated_revision": "r1",
      "revisions": [{
        "id": "r1", "parent": null,
        "direction": "Angular silhouette",
        "date": "2026-10-23T18:00:00Z",
        "reason": "First silhouette for the garden scene.",
        "preview_path": "artwork/review/garden-tree/r1.png"
      }, {
        "id": "r2", "parent": "r1",
        "direction": "Rounded canopy",
        "date": "2026-10-23T19:00:00Z",
        "reason": "Softer shapes fit the revised garden direction.",
        "preview_path": "artwork/review/garden-tree/r2.png",
        "disposition": "candidate"
      }],
      "events": [{
        "id": "decision-1", "type": "integration",
        "date": "2026-10-23T18:30:00Z", "revision_id": "r1",
        "reason": "Validated in the app before the direction changed."
      }, {
        "id": "decision-2", "type": "direction",
        "date": "2026-10-23T18:45:00Z", "direction": "Rounded canopy",
        "reason": "Move toward a softer garden silhouette."
      }, {
        "id": "decision-3", "type": "selection",
        "date": "2026-10-23T19:15:00Z", "revision_id": "r2",
        "reason": "Chosen for the next integration pass."
      }]
    }]
  }
}
```

Asset IDs are unique; revision/event IDs are unique within their asset. IDs use
1–64 letters, digits, dots, underscores or hyphens and start with a letter or
digit. `label`, `direction` and `reason` are explicit public plain-text summaries
(limits 100, 160 and 800 characters). They must not contain secrets; HTML escaping
does not redact text. Unknown fields are omitted from the site, but do not copy
the private journal wholesale into a potentially shared manifest.

Dates accept `YYYY-MM-DD` or `YYYY-MM-DDTHH:MM:SSZ`. The site orders revisions and
events chronologically. Parents must exist, be no newer than their children and
have no cycles. Omitted/null selection or integration displays **Not recorded**;
it does not assert that legacy artwork was never selected or integrated. The
site never infers these states from the newest image.
Non-null references must resolve within that asset. `events` is optional;
selection/integration/rejection events require an existing `revision_id`, while
direction events require `direction`. Referenced events cannot precede their
revision. Optional dispositions are `candidate`, `rejected`, `superseded` or
`retained`; selection and integration badges come from the separate pointers.
When disposition is omitted, the latest selection/integration/rejection event
for that revision supplies a rejected/candidate fallback (no events means
candidate). When making a decision, keep any explicit disposition and current
selection pointer consistent with the appended event. A rejected/superseded
revision cannot remain the current selection. Previously integrated artwork
can remain recorded as integrated while a replacement awaits actual app changes.

Every review export must be referenced, and every revision must use a distinct
preview path. Missing files, wrong kinds, duplicate IDs, invalid references,
cycles, size/hash failures or private paths fail the rebuild without replacing
an existing owned site. Older manifests without this feature continue to work.

## Build, inspect and resume

```sh
python3 deploy/preview.py build --release-output release-output
python3 deploy/preview.py serve --site release-output/site
```

Follow [PREVIEW.md](PREVIEW.md) for serving and optional sharing. Rebuilding copies
only verified public exports and allowlisted text; it never publishes the
journal or originals. Inspect the side-by-side desktop cards and stacked mobile
cards, selection/integration labels, chronological decisions and downloads.
The gallery is read-only: its controls do not persist selections or modify the
app. Make a requested decision in the journal, export its sanitized summary,
then rebuild. Report what was generated, selected and actually integrated as
separate outcomes, preserving previous directions and candidates for resume.
