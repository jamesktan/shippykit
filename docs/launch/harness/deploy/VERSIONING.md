# Versions and changelog

Every app ShippyKit ships keeps three things in step:

- **One marketing version, `MAJOR.MINOR.PATCH`**, the same on every platform. The first store release is `1.0.0`. Two-part versions such as `1.0` are not allowed.
- **Build numbers that only go up**: the iOS build (`CURRENT_PROJECT_VERSION`), the Android `versionCode`, or Unity's per-platform build numbers. Every upload needs a new one.
- **`CHANGELOG.md`** at the repository root. Each version has a dated section with the build numbers it shipped and the upload evidence. Each entry is one line saying what changed for the user, ending with `Evidence:` and the commit, file or URL that proves it.

`deploy/versions.py` reads the native project files (Xcode, Gradle, Unity), changes them, and checks the changelog. It never contacts a store.

## Quick path

1. Run `python3 deploy/versions.py status`.
2. Read the last lines:
   - **`NEXT [agent]`**: run the `$` command exactly as shown. If it contains `<…>`, fill in the value the message describes. Then go back to step 1.
   - **`NEXT [done]`**: the version state is correct. Carry on with the task.
3. If a command prints an error, report it and stop. Never edit version numbers in Xcode, Gradle or Unity by hand; use `versions.py set`, which changes every file and reads the result back.

## As you work

After each change a user would notice is committed, add an entry:

```sh
python3 deploy/versions.py note --kind Fixed --text "Sound comes back after a phone call" \
  --evidence <commit> --evidence release-output/results/<test output>
```

- **`--kind`** is one of `Added`, `Changed`, `Fixed`, `Removed`, `Security` or `Deprecated`.
- **`--text`** says what changed in words a player or customer understands. Leave out file names and internal refactors. Store "What's New" text is generated from these lines.
- **`--evidence`** names what proves it: the commit that made the change, plus a saved test result, screenshot or receipt where one exists. Repeat it for each piece. Every reference must exist; the command checks commits with git and files on disk. Never use a secret or a signed URL as evidence.

Changes that users cannot notice (refactors, tooling) need no entry.

## Before a build for the store

Run `status`. When the last released version already matches the project and there are new entries, it tells you to raise the version and build. Feature entries (`Added`, `Changed`, `Removed`, `Deprecated`) raise MINOR; fixes alone raise PATCH. A new MAJOR is the owner's decision (`--owner-approved-major`). Build numbers move to one above the highest build seen in the project or the changelog:

```sh
python3 deploy/versions.py set --bump patch --next-build
```

When the store's version record already exists with an older name (for example `1.0` before this rule), rename it to the new version when that build is uploaded. Apple requires the build's version to match the version record.

## After the upload is accepted

Close the version with the upload evidence:

```sh
python3 deploy/versions.py release --evidence release-output/apple-upload-receipt.json
python3 deploy/versions.py notes --store apple     # What's New text; --store google for Play release notes
```

`release` moves the `[Unreleased]` entries under `## [X.Y.Z] - <date>` and adds a `Builds:` line with each platform's build number and your evidence. `notes` prints the entries without their evidence and checks the store's limit (Apple What's New 4,000 characters, Play release notes 500). Apple shows no What's New for an app's first version. Put the text in the locale's `listing.md` under `## Release notes` through the store-copy skill, which also localizes it.

## Format

```markdown
# Changelog

## [Unreleased]

### Fixed
- Sound comes back after a phone call. Evidence: 3f2c1a9; release-output/results/audio-tests.txt

## [1.0.0] - 2026-10-29

Builds: iOS 7. Evidence: release-output/apple-upload-receipt.json

### Added
- Three random specials in every game. Evidence: 261a7d3; release-output/results/tests-build-7.txt
```

Released versions are listed newest first and are never edited afterwards; corrections go in a new entry. `status` reports entries without evidence, evidence that does not exist, missing dates and versions out of order.
