---
name: shippykit-store-copy
description: Draft, refresh, or naturalize Apple App Store and Google Play copy and release notes from verified app features. Use for focused copy changes, locale updates, or an initial listing; preserve unaffected human copy and produce validated text, a reviewable diff, and a refreshed local preview.
---

# ShippyKit store copy

Complete the requested copy change without starting a full release. Local drafting does not require store credentials, new builds, platform expansion, enrollment, or tool installation. Upload only when the user's existing instruction explicitly covers the intended store update and its publication effects.

## Resolve the app and requested change

1. Resolve the target repository from the task; the skill's installation directory is not the app root. Read its project instructions, existing listing files, change request, and any `deploy/APP.md`, `deploy/STATE.md`, relevant `deploy/APPLE.md` or `deploy/GOOGLE-PLAY.md`, and `deploy/PREVIEW.md`. Use these as references within this task's scope.
2. If those guides are absent, find the supplied ShippyKit package, defaulting to `~/Documents/ShippyKit`, and read its relevant `deploy/` guides and preview helper. A source checkout may keep them under `docs/launch/harness/deploy/`. Resolve actual paths; do not use relative links outside this skill or require the full harness to be bootstrapped. If unavailable, finish independent copy work and report the missing preview/reference step.
3. Establish requested platforms, locales, fields, tone, and whether this is an initial draft or an update. Infer routine facts from the app and existing copy. Preserve other locales, owner wording, links, and fields. Do not translate every locale or add a platform merely because it is supported. Ask only for a material ambiguity that existing evidence cannot resolve.

Once per chat, follow the resolved `deploy/START.md` startup/update protocol when available. An explicit copy or naturalization request routes directly to this task without a forced menu or release-scope expansion; a missing startup guide does not block independent copy work.

## Ground the copy in the real app

Record the source revision and any relevant uncommitted changes, target version/build, and baseline listing source. Inspect actual implementation, current UI/captures, tests, and release evidence for the features being described. Distinguish verified behavior from plans, source-only implementations, and features absent from the selected release. A remote listing read, when access already exists, helps establish the current baseline; label a local-only baseline as such.

For user-supplied photos, videos, logos or brand references, follow the resolved `deploy/MEDIA-INPUTS.md` to inspect attachments and retain a stable input index. Use the requested marketing purpose, approved overlay captions, existing asset relationships and any supplied brand brief to guide wording. Ground factual claims in the actual project, source documents and applicable user-approved facts; generic artwork or reference footage alone does not establish an app feature. Preserve input references in private copy evidence so later revisions retain their context.

Lead with what a person can accomplish, then concrete features that support that benefit. Keep the app's voice and useful existing copy. Avoid invented performance, privacy, accessibility, offline, pricing, awards, popularity, or compatibility claims. Do not invent support/privacy URLs or legal declarations. Mark unresolved facts in private notes and omit unsupported public claims.

Write release notes from actual user-visible changes relative to the previous release. Start from `python3 deploy/versions.py notes --store apple` (or `--store google`), which prints the version's changelog entries without their evidence; then localize and shorten as needed. Internal refactors alone do not justify a new feature or performance claim. Do not recycle future roadmap items as shipped changes. Keep promotional language out of Google Play release notes.

## Translate and naturalize only the requested locales

For locale-native phrasing, follow the resolved `deploy/LOCALIZATION.md` from the app or supplied package. Preserve product meaning while adapting idioms, register and sentence structure to the actual audience. Keep brand terminology, URLs, identifiers, quantities and commercial facts accurate; ask about material uncertainty. Marketing localization does not add app UI languages or justify claiming language support.

Lingo.dev is optional. Its current engine-backed `@lingo.dev/cli` differs from the legacy `lingo.dev` / `i18n.json` workflow; inspect and reuse the existing version/configuration rather than migrating implicitly. Obtain permission before new installation, account/engine changes or paid external content transmission unless already specifically authorized. Send only scoped public marketing text, preserve human translations, and independently review meaning and store counts. See [current CLI documentation](https://lingo.dev/en/docs/cli); lack of provider access does not block ordinary copy drafting.

Keep translation/rephrase provenance, source/target hashes, provider configuration evidence, review status and unresolved questions outside the public preview. Export localized values under the same supported Markdown headings below. For localized screenshot captions, reuse real captures and the existing compositor, verify typography and actual UI language, then update affected media hashes and preview; do not fabricate localized UI or replace unaffected media.

## Check current field rules and count the final text

Recheck the linked official references when performing the task; these limits were checked on 2026-10-23. Apply the selected platform's actual fields:

| Platform | Field | Limit |
| --- | --- | --- |
| Apple | Name | 2–30 characters |
| Apple | Subtitle | 30 characters |
| Apple | Promotional text | 170 characters |
| Apple | Description | 4,000 characters; plain text, no HTML |
| Apple | Keywords | 100 bytes; each keyword longer than 2 characters |
| Apple | What's New | 4,000 characters; unavailable for the first version |
| Google Play | App name / title | 30 characters |
| Google Play | Short description | 80 characters |
| Google Play | Full description | 4,000 characters |
| Google Play | Release notes | 500 Unicode characters per language |

Sources: [Apple app information](https://developer.apple.com/help/app-store-connect/reference/app-information/app-information), [Apple platform-version fields](https://developer.apple.com/help/app-store-connect/reference/app-information/platform-version-information), [Google Play listing fields](https://support.google.com/googleplay/android-developer/answer/9859152?hl=en), and [Google Play release notes](https://support.google.com/googleplay/android-developer/answer/9859348?hl=en).

Run actual counts over each final field value using an available interpreter or existing project tool; do not estimate. Exclude Markdown headings and notes, but include payload spaces, punctuation, separators, and line breaks. Count Apple keywords as UTF-8 bytes, for example `len(value.encode("utf-8"))` in Python. Report Unicode character counts and any store-specific counter differences; do not count emoji by visual appearance or silently truncate text. Google release-note language tags are transport wrappers, not note content. Keep enough headroom where a store's Unicode counting is uncertain and confirm its validation during an authorized upload. Record field, locale, measured count/unit, limit, and pass/fail. Fix over-limit text before declaring the draft ready.

## Save reviewable copy and refresh the preview

1. Save applicable files under the app's `release-output/stores/ios/<locale>/listing.md` or `release-output/stores/android/<locale>/listing.md`. Follow an established canonical listing source if one exists, and keep the release copy synchronized without creating competing sources of truth.
2. Use a `# Store listing` container and applicable public headings: `## Name` or `## Title`, `## Subtitle`, `## Promotional text`, `## Short description`, `## Description`, `## Keywords`, and `## Release notes` or `## What's New`. Use `Description` for Play's full description. Keep exact field text under each heading, without counts, annotations, or Markdown decoration intended only for the agent. Omit inapplicable fields. Check the installed preview helper's supported headings if its version differs.
3. Keep reviewer notes, claim evidence, counts, questions, and change rationale in separate files under `release-output/private/copy/`, outside `site/`. Do not place credentials in these files. Save a before/after diff against the actual baseline, or identify an initial draft with no previous copy. Explain substantive changes briefly and retain evidence references for new claims.
4. Update only affected entries in `release-output/manifest.json`, preserving unrelated data. Each public listing entry needs release-root-relative `path`, `kind: "store_copy"`, actual file `sha256`, `bytes`, `platform` (`ios` or `android`), and `locale`. Create a compatible manifest only if absent. Hash the saved bytes after final edits; never mark private notes as `store_copy` or `preview_copy`.
5. Follow the resolved `deploy/PREVIEW.md` to rebuild the local site with the existing helper, using the target app's release-output directory even when invoking the helper from the package. Verify that changed public sections appear and private material is absent; preserve existing media and unrelated preview processes. Missing helper/runtime blocks only preview verification, not drafting, and does not authorize an install. Do not claim a stale or unbuilt preview is current. Public sharing is a separate opt-in governed by that guide.

Update existing APP/STATE copy and preview evidence where applicable; do not create a full deployment scaffold just for this task. Finish with changed paths/locales/fields, the reviewable diff, count results, preview location/status, and unresolved facts.

## If a store update is explicitly requested

Follow the app's platform playbook and reuse authorization that covers the actual action. Read current remote app/version/locale and metadata before writing; avoid overwriting newer owner changes. Check field editability and publishing behavior: Apple promotional text can change without a new submission, and Google listing edits are not isolated simply by choosing a testing track. A save, edit commit, or review action may affect live metadata. If the requested draft cannot remain nonpublic, explain the concrete effect and obtain permission for that effect before writing.

Write only the agreed fields/locales. Do not upload a binary, submit for review, release, change pricing, or enroll an account as an implicit consequence of a copy refresh. After an authorized mutation, read back the exact fields and observed store state, save IDs/time/evidence outside the public preview, and distinguish saved, pending review, and live. On an ambiguous response, read before retrying. A locally validated draft is not proof of upload or publication.
