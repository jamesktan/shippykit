# Naturalize marketing copy

Use this guide for requested store locales, promotional copy and screenshot captions. Naturalization means preserving the product's meaning while choosing phrasing, register and cultural references that fit the target audience. Lingo.dev is an **optional provider**; ordinary drafting and locale review can proceed without it. This workflow does not add runtime languages, modify app resources, create accounts, or upload store metadata implicitly.

Read the app's APP/STATE, canonical listing sources and existing translations. Confirm the requested platform, market, language/script/region, fields and public claims. A translated listing is not proof that the app UI, help, support or audio supports that language. Preserve valid human translations and unaffected locales. Ask only about unresolved audience, terminology, commercial facts or scope.

## Choose the installed Lingo generation

Official references checked **2026-10-24**; recheck the installed version and current docs before execution.

| Existing setup | Follow |
| --- | --- |
| Current `@lingo.dev/cli`, executable `lingo` | Node.js 22+; `.lingo/config.json`, `.lingo/lock.json`; engine-backed `push` / `pull`. [Current CLI](https://lingo.dev/en/docs/cli), [quickstart](https://lingo.dev/en/docs/cli/quickstart). |
| Legacy `lingo.dev` package / `i18n.json` | Preserve its pinned commands, `i18n.json` and `i18n.lock`. Legacy buckets, key-path syntax and authentication differ. Do not run new commands against it or migrate automatically. [Legacy configuration](https://docs.lingo.dev/config), [legacy authentication](https://docs.lingo.dev/auth). |
| No provider setup | Prepare source copy, terminology and the review plan locally. Explain the concrete missing prerequisite; provider setup is not required to finish ordinary copy work. |

Inspect package manifests/locks and existing configuration first. For an installed CLI, read `node --version`, `lingo --version` and `lingo --help`; do not use an unpinned `npx` invocation to discover whether it is installed. Reuse the existing organization, engine, config and lockfile. Do not connect repository-wide automation as part of this task.

Before a new install, account/engine change, or paid/external translation, explain the chosen CLI/version/install location, exact files/locales to transmit, provider/model route and expected usage or unresolved cost. Obtain permission unless existing authorization already covers those actions. A request to research Lingo.dev is not permission to transmit project content. Exclude private notes, reviewer credentials, account responses, unpublished sensitive material and unrelated app source. Keep credentials in the existing secure mechanism, never chat or committed config.

For an approved new setup only, the official installation is `npm install -g @lingo.dev/cli` (select and record the agreed version). `lingo login` establishes a session; `lingo init` writes localization configuration; `lingo link` selects an organization/engine and can create resources, so choose existing resources unless creation is authorized. Noninteractive use supports the secure `LINGO_API_KEY` environment reference. Never print its value or pass a literal key in recorded commands. [Setup](https://lingo.dev/en/docs/cli/quickstart), [authentication and linking](https://lingo.dev/en/docs/cli/commands).

## Shape the voice without changing the facts

Prepare a short locale brief: actual audience, benefit, preferred formality, brand tone, established terminology, and examples of acceptable wording. Adapt idioms, sentence rhythm and calls to action where meaning survives; do not invent local endorsements, awards, prices, capabilities or cultural claims. Keep URLs, identifiers, placeholders, version numbers, quantities and commercial meaning intact. Formatting a number is different from changing its value or converting a price.

Lingo engines provide complementary controls:

- **Brand voices:** locale-specific tone and register; an engine selects one matching voice text. Preserve the owner's choices about formal/informal address. [Brand voices](https://lingo.dev/en/docs/platform/brand-voices).
- **Glossaries:** approved translations and non-translatable brand/product terms. Review terminology collisions rather than adding contradictory entries. [Glossaries](https://lingo.dev/en/docs/platform/glossaries).
- **Rules:** concrete locale conventions, punctuation and wording constraints. Include store-field limits as guidance, then independently measure outputs. [Rules](https://lingo.dev/en/docs/platform/rules).
- **Optional natural-copy rephrase:** the async localization pipeline can rephrase marketing text and run a back-translation check. This is not a generic CLI `--rephrase` flag; the synchronous `/localize` route does not run pipeline stages. Verify the chosen integration uses that async path and inspect its actual stage results. A job can finish with warnings after rephrase fails. Keep legal/privacy declarations out of stylistic rewriting. [Pipeline](https://lingo.dev/en/docs/api/pipeline), [rephrase behavior](https://lingo.dev/en/docs/api/pipeline/rephrase).

Voices, glossaries and rulesets are shared organization resources: changing one can affect other attached engines. Read current attachments and stay within the authorized configuration scope; do not retune a shared production engine just for one caption. An AI quality score is useful evidence, not independent human approval or proof of store compliance. [Engine ownership](https://lingo.dev/en/docs/platform/engines), [AI reviewers](https://lingo.dev/en/docs/platform/ai-reviewers).

## Keep the payload narrow

Prefer a small structured staging payload containing only public field values and approved overlay text. Retain the project's canonical source; staging is an input/output bridge, not a second authority. JSON keys let the final exporter preserve preview-compatible Markdown headings instead of translating the parser's headings. Markdown is supported too, but requires that same structural check. [Formats](https://lingo.dev/en/docs/cli/formats).

Example for a **new, explicitly scoped iOS marketing configuration**; replace placeholder IDs and select only requested locales. Do not overwrite an existing config with this example. An existing wider setup needs a reviewed marketing-only binding or other version-supported locale scoping before running; positional file patterns alone do not narrow its target locales.

```json
{
  "orgId": "org_REUSE_EXISTING",
  "engineId": "eng_REUSE_EXISTING",
  "sourceLocale": "en-US",
  "targetLocales": ["fr-FR", "de-DE"],
  "files": [
    {
      "pattern": "marketing-copy/en-US/ios.json",
      "lockedKeys": ["invariants.brand", "invariants.supportUrl", "invariants.privacyUrl", "invariants.version"]
    },
    {
      "pattern": "marketing-copy/en-US/overlays.json",
      "lockedKeys": ["captureIds"]
    }
  ]
}
```

Here `ios.json` separates `invariants` from fields such as `copy.subtitle` and `copy.description`; `overlays.json` pairs real capture IDs with caption text. Use actual app facts, not sample marketing claims. Add an Android payload only for requested Android copy. The CLI substitutes the source locale in paths, producing e.g. `marketing-copy/fr-FR/ios.json`. Confirm each provider locale maps to a supported store locale; matching language names do not guarantee identical store identifiers. [Configuration](https://lingo.dev/en/docs/cli/configuration), [locale handling](https://lingo.dev/en/docs/cli/locales).

For JSON/JSONC, `lockedKeys` copies source values unchanged; `preservedKeys` protects existing target values. Preserved keys can initially be seeded from source, so their presence does not prove translation. Record reviewed human fields and deliberately protect or exclude them. These controls do not apply to Markdown prose. [Key controls](https://lingo.dev/en/docs/cli/key-controls).

After approved setup and an inspected payload, run from the configured project directory:

```sh
# First fill: whole target files that do not yet exist
lingo push 'marketing-copy/en-US/ios.json' 'marketing-copy/en-US/overlays.json' --backfill-missing --wait

# Later source changes: translate changed content, then write results
lingo push 'marketing-copy/en-US/ios.json' 'marketing-copy/en-US/overlays.json' --wait
```

`--backfill-missing` does not fill new keys in existing target files. Ordinary updates can replace human edits whose source changed; preserve a reviewable baseline and inspect the diff. Avoid `--force`, purge, and automatic conflict resolution. Retain `.lingo/config.json`, `.lingo/lock.json` and accepted translations together under the project's commit policy. After interruption, inspect the recorded run and use `lingo pull` from the same checkout/machine before resubmitting; it writes outputs and may conflict with local changes. [Push semantics](https://lingo.dev/en/docs/cli/push), [existing translations](https://lingo.dev/en/docs/cli/existing-translations), [run state](https://lingo.dev/en/docs/cli/configuration).

The [static-content guide](https://lingo.dev/en/guides/static-content) documents `lingo check` for freshness without file writes. Use it only if the installed version exposes that command; do not substitute a translating push for a missing check. Freshness is separate from linguistic quality, accurate claims and store acceptance.

## Review, export and resume

1. Compare each target field against the verified source and the previous human version. Check meaning, benefit, regional usage, grammar, tone, glossary terms, URLs, numbers and placeholders. Use a separate review pass; request a qualified locale reviewer when uncertainty remains material. Say whether review was agent-only or human; do not describe machine output as native-speaker approved. A back-translation is a drift signal, not proof by itself.
2. Run actual counts on the final field values using the store-copy skill's current Apple/Play limits and official references. Check Unicode/UTF-8 byte limits, keyword separators, platform fields and locale availability. Shorten naturally when needed; do not truncate or add unsupported claims to satisfy limits. Preserve reviewer notes separately. [Apple fields](https://developer.apple.com/help/app-store-connect/reference/app-information/platform-version-information), [Play listing fields](https://support.google.com/googleplay/android-developer/answer/9859152?hl=en).
3. Save reviewed public copy at `release-output/stores/{ios,android}/<store-locale>/listing.md`. Keep supported headings such as `## Subtitle`, `## Description` and `## Release notes` unchanged for the preview parser; localize their field values. Synchronize any established canonical listing source and retain a before/after diff.
4. Render approved captions through the existing deterministic screenshot compositor using original real captures. Preserve originals and in-app pixels; do not paint a translated UI onto an app that lacks it. Record the actual UI language separately from caption/marketing locale. Check fonts, shaping/RTL, line breaks, clipping and legibility at actual export sizes. A caption-only change need not rebuild the binary; a requested UI localization is a separate development/build/capture task.
5. Update affected public manifest entries only: release-relative path, actual SHA-256/bytes, platform, locale; `kind: store_copy` for listing Markdown and `kind: app_store_screenshot` for genuine composed store screenshots, plus image dimensions. Promotional variants remain `promo_image`. Follow [PREVIEW.md](PREVIEW.md) to refresh and inspect all affected locale copy and overlays; never publish private translation evidence or label captions as localized app functionality.
6. Save provenance outside the public site, e.g. `release-output/private/copy/localization-<run>.json`: source/app revision, source and prior-target hashes, requested locales and store mappings, actual provider/CLI version, org/engine references, configuration/lock hashes, observed model and voice/glossary/rules/pipeline configuration version or timestamped snapshot/hash, job/stage results, reviewer identity/type, field counts, approved edits and final output hashes. Mark unavailable provider version details unknown; engine ID alone is not immutable configuration provenance. Keep credentials and raw private responses out.

Update APP/STATE with completed locales, unresolved wording/facts, pending provider jobs and the exact next action. Distinguish generated, reviewed, locally previewed, uploaded and remotely accepted. No provider setup or translation run authorizes store writes, new UI languages, review submission or publication; those retain the existing playbook and user scope.
