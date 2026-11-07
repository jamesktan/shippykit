---
name: shippykit-images
description: "Generate, revise and compare app artwork, game assets, icons and marketing media for ShippyKit projects. Use uploaded photos, video clips, logos, audio and screenshots in truthful marketing compositions; preserve originals and revision history."
---

# ShippyKit images

Create the requested visual assets and make them usable in the target project. This can run independently of a full ShippyKit deployment. Resolve the app repository from the request; read its instructions, existing assets and any `deploy/APP.md` / `deploy/STATE.md`. Use the supplied ShippyKit package (default `~/Documents/ShippyKit/`) for missing reference guides. Do not require store access, Cua Driver or another platform just to generate local artwork.

Follow `deploy/START.md` once when first entering ShippyKit in a chat for the version notice and task menu. An explicit artwork request already chooses the route; proceed without making the user choose again.

## Choose the right artifact

Infer the app's purpose, audience, palette and visual identity from the actual app and the user's direction. Inspect existing artwork before deciding what needs changing. Resolve material ambiguity such as which existing image to replace; otherwise proceed with a concise brief and preserve unrelated assets.

When the user supplies media, follow `deploy/MEDIA-INPUTS.md` (or the package's guide). Resolve and inspect the actual accessible attachments/files, retain immutable originals under `release-output/inputs/<stable-id>/`, and maintain the private `inputs/index.json` with hashes, roles and derivative links. Distinguish reference, edit target, verified app capture and finished art; infer routine choices and ask only about unresolved material facts/access. Supplied media for the requested marketing task needs no blanket reuse confirmation. Reuse or transform it with the appropriate image/native composition tools, preserve intended audio, and never call generic artwork an actual app screenshot.

| Requested result | Approach |
| --- | --- |
| App icon | Follow the project's `deploy/ICONS.md` or the package's `deploy/ICONS.md`: reuse valid branding, generate when needed, export and wire actual target assets before the final build. |
| In-app artwork, backgrounds, illustrations or sprites | Generate or edit artwork to fit the real layout and runtime requirements. Preserve the app's native vector/code asset format when extending an existing system. |
| Marketing from uploaded photos, clips, logos, audio or brand references | Follow MEDIA-INPUTS.md; retain originals, compose/edit the supplied media within the brief, inspect exported frames/audio and keep private inputs out of the public site. |
| Feature graphic, campaign image or promotional variant | Generate appropriate artwork and compose accurate benefits, using actual product imagery when representing app behavior. Keep promotional exports separate from store screenshots. |
| Store screenshots with captions or device framing | Use supplied or existing captures of the real target app that match the intended release; capture fresh UI only when missing or stale. Preserve the captured UI; place it in a designed composition with truthful text. Do not synthesize nonexistent screens, features or gameplay and call them screenshots. |

Use built-in `image_gen` for new raster art and creative image edits, following the available imagegen skill when present. View local reference/edit images first; distinguish reference images from edit targets and specify what must stay unchanged. Existing vector edits and deterministic export/layout work can use the project's installed native tools. Missing tools require the existing ShippyKit setup permission gate. If generation is unavailable, disclose that and ask before a paid CLI/API fallback; never silently switch providers or request secrets in chat.

## Generate, integrate and inspect

Write a short brief with intended use, real product facts, composition, palette, reference roles, exact text if any, output dimensions and background/alpha needs. Keep a consistent visual direction across requested variants. Request actual transparency when needed. Inspect results at full size and at their intended display size; check text, edges, safe areas and contrast before accepting them. Make targeted corrections rather than producing unrequested batches.

Follow `deploy/ASSET-REVISIONS.md` for every generated or edited asset. Resume the existing asset's stable ID, brief, direction and history before generating. Preserve each candidate/master with its own revision ID and path, parent revision, actual creation time, direction and reason for the change. A change of direction branches from the relevant reference; it does not erase prior attempts. Keep the full prompts, references, hashes and generation evidence in the private journal. Do not invent history when adopting old artwork: record it as an observed baseline with unknown generation details.

Link supplied inputs as observed baselines and retain each edit/overlay as a new revision. Originals and the input index stay private; even a review of the original appearance needs a separate inspected export under `artwork/review/`. Export prepared promo media and sanitized revision summaries, then refresh the website after the batch.

Record selections and rejections with reasons, preserving earlier decisions. Retain originals even when replacing the active runtime file; deletion requires an actual cleanup request. Export sanitized review images and the public history for the website after each generation/refinement batch or direction change, including alternatives rather than only the final choice. Keep `selected_revision` separate from `integrated_revision`; selection alone proves neither import nor a verified build.

Put selected runtime assets in the app's existing resource pipeline and verify their actual references, import settings and rendering. Update the integrated revision only after those checks, with the exact export hash and evidence. Rebuild the affected app when runtime artwork or icons change; mark previous build evidence stale. A marketing-only image update does not require a new binary. Store exports must meet current official requirements for their platform and locale; consult [Apple screenshot specifications](https://developer.apple.com/help/app-store-connect/reference/app-information/screenshot-specifications) or [Google Play preview assets](https://support.google.com/googleplay/android-developer/answer/9866151?hl=en) when preparing those destinations.

Save release deliverables using the project's existing conventions:

- `release-output/icons/`: icon master and platform exports, as specified by ICONS.md.
- `release-output/inputs/`: immutable supplied originals and private index; never public gallery entries.
- `release-output/artwork/`: generated artwork masters and selected exports when no existing equivalent exists; runtime references use the app's resource location.
- `release-output/artwork/revisions.json`: durable asset/revision/direction journal; internal provenance remains private. `artwork/review/` contains sanitized revision previews for the website.
- `release-output/stores/<platform>/<locale>/`: verified store compositions from real captures.
- `release-output/promo/`: campaign images and videos, including public display versions of generated artwork when requested.
- `release-output/evidence/`: concise generation brief, actual prompt/reference roles, tool used, source/output hashes, export commands and integration checks. Keep these internal records outside `site/`; do not invent unavailable model or rights information.

Extend `release-output/manifest.json` without dropping other entries. Record actual relative path, kind, SHA-256, bytes, platform/locale and media dimensions. Mark selected public exports as `promo_image`, `promo_video`, `app_store_screenshot` (either mobile platform), or the icon kinds from ICONS.md. For Google Play listing images, also record `play_image_type` and `order` as described in GOOGLE-PLAY.md's Play helper section. Revision review exports use `asset_revision_preview` and the explicit `asset_history` contract in ASSET-REVISIONS.md. Preserve a separate kind such as `app_artwork` for runtime/master assets that are not intended for public preview. Do not relabel private sources to make the gallery include them.

Follow `deploy/PREVIEW.md` to refresh and verify the local asset website after changing release exports. If the app has no helper yet, copy only the relevant preview files from the package; do not start a full deployment. Keep ngrok opt-in. If copy needs changing too, use `shippykit-store-copy` within the user's scope and keep captions consistent with the selected listing.

Checkpoint the active direction, selected and integrated revisions, pending alternatives and journal path in STATE.md. Finish with the saved assets, actual prompt or prompt-file reference, comparison/history website, integration/preview checks and any unresolved generation or build prerequisite. Preserve existing commit/push instructions. Image generation alone does not authorize store uploads, live listing edits or public sharing; use the applicable deployment playbook and existing authorization if those actions were requested.
