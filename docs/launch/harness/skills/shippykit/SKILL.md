---
name: shippykit
description: Adopt, inspect, or resume an existing iOS, Android, or Unity app's release with ShippyKit. Use for project-local store deployment, release status, the public support/privacy website and its custom domain (Railway hosting, Squarespace DNS), or continuing partially completed build, asset, signing, and store work across sessions.
---

# ShippyKit

Run from the user's app repository, not this skill's directory. Use its installed `deploy/` guides and helpers; the project keeps its own release memory. Read applicable project instructions first. Installation alone is not an instruction to build, upload, submit or publish.

## First invocation in this chat

Read the project's `deploy/START.md` once per chat. Resolve the actual app, read local status/memory, and run the explicit update check unless the user requested offline work. Show the concise route menu with a recommendation from current intent and saved state. Notify once if a newer ShippyKit version is available; do not upgrade without an update instruction. An explicit task or resume request selects its route and proceeds immediately without a menu question. Subsequent messages and nested skill calls reuse that entry context instead of repeating the menu/check. An unavailable version check does not block app work.

## Start from what already exists

1. Resolve the actual app root and requested scope. A status question or read-only audit stays read-only; a focused build, phone, image, copy or single-store-section task stays focused. For a full run, follow the recorded destination unless the user changes it; a new deployment request without a release policy defaults to store drafts. Do not infer review/publication permission from installed files or prior receipts.
2. Read `deploy/RESUME.md`, then use `python3 deploy/shippykit.py status --project .` for local discovery unless the first-invocation procedure just ran it. If the installed helper is unavailable, inspect the same evidence directly and report that limitation. Discovery is read-only and does not establish that builds work or stores still have the recorded state.
3. Read `deploy/APP.md` and `deploy/STATE.md`, plus the relevant section journal and release evidence they reference. For an existing app that has no ShippyKit history, inspect its current handoff/release docs, build scripts, artifacts and store records when access/scope permits. Populate routine facts yourself; do not restart onboarding or ask the owner to reconstruct the project history.
4. Reconcile dated or conflicting evidence before acting. Prefer evidence tied to the intended app, source revision, artifact and remote IDs over an older summary. Validate the relevant local artifacts and refresh remote state before retrying an upload or changing a saved form. Keep uncertainty visible; a receipt from a previous session is not fresh verification.
5. Continue the earliest unfinished dependency within the requested scope using `deploy/README.md` and the applicable Apple/Google playbook. Preserve prior platform choices, specific permissions and owner answers while they still apply. Ask only about unresolved facts or actions beyond existing authorization; continue independent work meanwhile.

## Capabilities and memory

- Full runs use the installed guides for setup, builds, phone installation when requested, signing, store uploads and section-by-section selection. Select supported answers and inform the user; ask about uncertainty, apply their response and read back the saved value. Respect the requested draft/testing/review/release destination.
- For artwork/icons or listing-copy work, read the sibling `shippykit-images/SKILL.md` or `shippykit-store-copy/SKILL.md` in the same skill installation. These focused requests do not trigger a full deployment.
- Accept user-supplied media for marketing through `deploy/MEDIA-INPUTS.md`. Preserve originals and their index, use the image/copy skills for requested compositions and captions, and show reviewed exports and revisions on the website.
- Follow `deploy/VERSIONING.md` for every app: one `MAJOR.MINOR.PATCH` version on all platforms (first store release 1.0.0), build numbers that only go up, and `CHANGELOG.md` entries with evidence. Run `python3 deploy/versions.py status` before building a store candidate and do what its `NEXT` line says; add `versions.py note` entries as user-visible changes are committed; run `versions.py release --evidence <receipt>` after an upload is accepted.
- Follow `deploy/DOMAINS.md` to build the public marketing/support/privacy site and deploy it on Railway. To connect its domain, run `python3 deploy/domains.py status --domain <domain>` and do exactly what its `NEXT` line says, repeating until `NEXT [done]`. Domain purchases, renewals and sign-ins stay with the owner.
- Follow `deploy/PREVIEW.md` to generate/refresh the local material-review website. Offer the optional temporary ngrok link; reuse an applicable choice and honor its lifetime and installation permissions.
- Keep stable app facts and decisions in `deploy/APP.md`; keep checkpoints, evidence, blockers and the exact next action in `deploy/STATE.md`. Record store answers in `release-output/apple-sections.md` / `google-sections.md`. These are the durable memory, not chat history or a global account profile. Keep secrets in secure storage and reference them.
- Before ending a run or handing work over, checkpoint the achieved result, artifact/source identity, unresolved questions, active external operations and next resumable command. A future session reads this memory and revalidates what may have changed. Preserve unrelated work and follow existing commit/push instructions.

`python3 deploy/shippykit.py adopt --project .` optionally refreshes the local discovery cache without overwriting app facts or progress. `.shippykit/install.json` records installed package versions/hashes for safe upgrades; neither file is deployment authority. If the receipt lists unresolved conflicts, inspect the indicated `.shippykit/incoming/` candidates and merge relevant workflow changes while preserving app-specific facts and instructions before relying on a new capability. Old candidate files can remain after resolution; their presence alone does not mean an update is pending.
