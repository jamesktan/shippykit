# ShippyKit 0.2.x verification

Verified on 2026-10-24 UTC. This update adds asset revision review, user-supplied marketing media, the startup menu, advisory version checks and an optional Lingo.dev marketing-localization workflow.

The live version check found that the official repository is private. Version 0.2.1 adds a read-only fallback through an already authenticated GitHub CLI when the anonymous version request returns an access/not-found response. A live check against Isofall's existing 0.1.0 receipt correctly detected the newer published version using that route without changing the app. No login, installation or automatic upgrade is performed.

## Automated checks

All 90 Python tests passed on macOS Python 3.9.6 and Python 3.14.8: 20 installer, 19 resume, 20 update-check and 31 preview tests. Update tests simulate the network and CLI, including newer/equal/older versions, prerelease ordering, malformed and oversized responses, interruption, timeout, inaccessible private repositories and unavailable receipts. They verify that checks do not modify project files or make ordinary status contact the network.

```sh
/usr/bin/python3 -m unittest discover -s tools -p 'test_shippykit_*.py' -q
python3 -m unittest discover -s tools -p 'test_shippykit_preview*.py' -q
bun run docs:check
```

Documentation checks passed, including package-local links and skill YAML/frontmatter validation with the installed Ruby YAML parser. The optional skill-creator validator could not run because its interpreter lacks PyYAML; no dependency was installed for this check.

## Revision website

A temporary synthetic fixture contained three distinct rendered cube images: r1 marked integrated, r2 rejected, and a new direction r3 selected while integration remained r1. Four chronological decision events and English/French public listings were included. These were interface fixtures, not generated game assets or claims about a real app's integration state.

Using the already installed isolated Playwright Chromium, the generated site was inspected at 1440×1000 and 390×844. All images decoded, the selection/integration badges and decision timeline matched the fixture, and there was no horizontal overflow or page script error. Desktop and phone screenshots were visually inspected. Direct file opening also worked.

Private master/journal/prompt sentinels and unknown private history fields were absent. The loopback server returned 404 for source manifest, journal, master and generated registry requests. Its owned session was stopped after checking; no tunnel or public publication was started. Regression tests additionally cover invalid references, cycles, dates, duplicate IDs, rejection/reselection, symlinks, tampering, existing-site preservation and older manifests.

Uploaded-media regression fixtures verify that prepared promotional images/video are included, while `inputs/` originals and the private index are excluded and cannot be relabelled as public assets. The resume helper recognizes changes to the input index without scanning original files or exposing their names. No actual user media was supplied or transformed during this harness update.

## Upgrade and workflow review

A temporary project was installed from the committed 0.1.0 package, then upgraded to 0.2.0. App facts, decisions and the artwork journal remained byte-identical. A customized preview guide stayed in place with the new guide recorded as an incoming conflict. All six Codex/Claude skill entrypoints and the three new guides were installed; a repeated installation preserved the same project data.

The same fixture then upgraded to 0.2.1 with the media guide. Six existing app-memory, customized-guide, asset-journal and uploaded-original/index files remained byte-identical.

An independent agent reviewed generic startup, focused requests, resume, offline status, update states, branched artwork and a legacy Lingo setup with reviewed translations. Explicit task scope and prior authorization remain intact. The Lingo workflow was checked against linked official documentation; no Lingo installation, account change, billed translation, store upload or runtime localization was performed by this verification.
