# Use supplied media in marketing assets

Use uploaded photos, video, logos, audio, brand references, screenshots or finished artwork within the requested marketing task. Follow the image skill, [asset revisions](ASSET-REVISIONS.md) and [preview workflow](PREVIEW.md). A focused media task does not start a deployment. Supplying files for that task authorizes normal reuse, editing and composition; do not ask for blanket permission again.

## Resolve and preserve the inputs

1. Resolve actual attachments or local files available through the host's tools. Inspect what is accessible before asking for a missing file. An attachment name or earlier chat mention is not proof its bytes are still available. Ask for a usable attachment/path only when access is missing; continue independent work.
2. Inspect file signatures and actual content, not just extensions. View images; sample video frames and inspect its timeline/audio; inspect audio streams and listen where a playback tool is available. Record an unverified listening step honestly. Read relevant supplied brand instructions.
3. Assign a stable input ID and copy original bytes into `release-output/inputs/<stable-id>/original.<actual-extension>`. Verify the copied SHA-256 and byte size. Never edit, transcode, rename over, or strip metadata from this retained original. Keep original filename and metadata evidence in the private index.
4. Maintain `release-output/inputs/index.json` atomically. Reuse an existing input identity when its bytes and source match; retain additional source references when appropriate. Same filename with different bytes is a new input, not a replacement. Preserve earlier entries and derivative links on resume.

The internal index uses `schema_version: 1` and an `inputs` array. Each entry records:

| Field | Evidence to retain privately |
| --- | --- |
| `id`, `path`, `original_filename` | Stable identity, retained path relative to release-output, original supplied name. |
| `sha256`, `bytes`, `media_type`, `observed_at` | Actual copied bytes, detected type and observation time; not an invented creation date. |
| `source` | Attachment/local-file origin and accessible reference; do not copy credentials, access tokens or signed URL query strings into the index. |
| `role`, `intended_use` | Inferred or user-specified role below, and the requested destination/composition. |
| `facts` | Observed dimensions/orientation, alpha, duration, codecs, audio streams and other relevant metadata; identify unknowns. |
| `known_constraints` | Supplied brand/license/use limits and the evidence for them; do not invent rights or authorship. |
| `derivatives` | Append `{asset_id, revision_id, path}` links to retained edits, compositions and review exports. |

`inputs/`, its index and private source/metadata evidence are never public manifest assets. Do not expose original filenames, source locations or private notes in the gallery. Keep these originals and records out of commits or sharing unless their disclosure is separately in scope.

## Infer the brief and each file's role

| Role | How to use it |
| --- | --- |
| `reference` | A mood, palette, brand, composition or sound reference; it need not appear in the output. Preserve the distinction from an image to edit. |
| `edit_target` | The actual photo, logo, clip or audio to transform; identify the subject/mark/content that must remain unchanged. |
| `app_capture` | Evidence of the real target app. Verify the represented app/device/release where relevant; preserve truthful UI and gameplay in screenshot or video compositions. |
| `finished_art` | Existing finished artwork or media to reuse, export or compose. Do not regenerate it merely because a generation tool is available. |

Infer ordinary choices from the request, file contents, app facts and brand material. State a short brief: roles, audience, destination, dimensions/aspect ratio, composition, exact text, crop/orientation, transparency and audio intent. Ask only when a material role, required content, missing access or consequential constraint cannot be resolved. Reuse earlier answers.

Generic uploaded art or footage is not automatically an app capture. If provenance is insufficient for a requested store screenshot, establish the actual app evidence or capture fresh UI. Never paint nonexistent screens/features, relabel unrelated artwork as real gameplay, or claim a different platform's capture represents the target app.

## Make the requested derivatives

- Use built-in `image_gen` for creative raster/photo edits, following the available imagegen skill and tool requirements. View local references first, pass the actual edit targets/references, and identify what to preserve. Keep the supplied original immutable; save each output as a new revision.
- Use installed native compositing/vector/export tools for deterministic captions, frames, layout and brand marks. Use installed transcoding tools for trims, sizing, orientation and overlays on real footage. Check tool availability and fonts before promising an export; missing tools follow the existing [setup permission gate](README.md#first-platforms-setup-and-permission).
- Inspect display orientation versus encoded dimensions, crop/safe areas, subject framing, edge quality and alpha. Request real transparency when needed; check the actual exported result, not a checkerboard-looking background. Preserve logo geometry and exact supplied text unless changing them is requested.
- Keep original clip audio unless the brief calls for a change. Inspect synchronization, levels, clipping, codec/container, duration, channels and sample rate as relevant. Do not silently add unrelated copyrighted music, discard the user's audio, or claim an unheard track was reviewed. Supplied audio may be incorporated into a requested promotional video.
- Honor known use/brand constraints. Ask only when a material uncertainty affects this deliverable or destination; do not impose a generic rights attestation on every upload.
- Do not fetch a source URL merely because it appears in metadata, or send inputs to a new external/paid provider without existing scope covering that action. A requested accessible URL source can be retrieved within its authorization. Normal requested transformations with the authorized tools need no redundant consent; ask before an uncovered fallback.

## Retain revisions and show reviewed outputs

Adopt the import into `artwork/revisions.json` as an observed baseline linked to its input ID/hash. Date the observation today if original generation details are unknown; do not invent a prompt, model, provider or historical generation date. Follow [ASSET-REVISIONS.md](ASSET-REVISIONS.md) for stable IDs, parentage, direction and selection events. Append every new edit/overlay as a retained revision and link it back in the input index. A new direction preserves all prior candidates and originals.

Export only inspected public derivatives:

- Sanitized comparison copies under `artwork/review/<asset-id>/<revision-id>.<ext>` use `asset_revision_preview` and the public `asset_history` contract. To show an original's appearance for review, make a separate inspected copy here; never point the gallery at `inputs/` or the retained original.
- Prepared campaign images/video under `promo/` use `promo_image` / `promo_video`. Real app screenshot compositions use the appropriate store paths/kinds after verifying destination requirements. Audio-only inputs remain private sources; the current gallery can play their inclusion in a prepared video, not arbitrary raw audio files.
- Inspect each export's pixels/frames, text, metadata and audio where applicable. Remove private metadata from the public derivative, preserving the original and its metadata evidence. Record actual SHA-256, bytes, dimensions and duration/encoding in the existing manifest without dropping other entries.

Refresh the [local preview website](PREVIEW.md), inspect desktop/mobile output, playback and downloads, and verify that originals/index/private evidence are absent. Keep sharing, store upload and provider changes within their existing scope. Checkpoint input IDs, roles, derivative/revision links, chosen output and unresolved checks in STATE.md. Report what was reused or transformed and where the preserved originals, revisions and reviewed outputs live.
