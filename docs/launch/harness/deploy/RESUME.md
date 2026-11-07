# Resume an existing app

Start from the app's current stage. Installing or copying ShippyKit does not authorize a rebuild, replace existing decisions, or establish that any upload succeeded.

## Discover without changing the project

Run the installed helper from the app repository, or supply the actual app directory:

```sh
python3 deploy/shippykit.py status --project .
python3 deploy/shippykit.py status --project . --json
python3 deploy/shippykit.py status --project . --json --verify-hashes
```

Python 3.9 or newer and the standard library are sufficient. `status` writes no project files, makes no network calls, runs no builds and installs nothing. It observes Git locally without listing remote URLs or credential configuration. It does not inspect environment variables, keys or global personal directories.

The scan stays within the supplied project. It finds nested Xcode, Gradle/Android and Unity markers and identifies declared framework clues. A project file or dependency declaration remains unverified evidence of a runnable platform target. Discovery skips symlinks, dependencies, caches and build trees; it inventories known artifacts under `release-output/` separately without descending into app bundles or archives. Limits are explicit in JSON. If the selected directory contains several products or a limit hides the real target, narrow `--project` to the intended app rather than scanning the user's home directory.

The default checks artifact presence and recorded sizes. `--verify-hashes` streams manifest SHA-256 checks, capped at 32 MiB per file and 128 MiB total, including memory fingerprints. A skipped check remains unverified; a missing file or mismatched size/hash is reported separately. Large archives and directory tree hashes require the project's existing validator. `files[]` and `artifacts[]` manifests are supported. No manifest claim is treated as fresh remote verification.

To save the sanitized inventory explicitly:

```sh
python3 deploy/shippykit.py adopt --project . --json
```

`adopt` writes only `.shippykit/discovery.json`. It preserves APP.md, STATE.md, journals, release artifacts and source files. The discovery snapshot is a disposable local cache, never an authorization record or a completed-stage marker. A later status can identify changed memory fingerprints against it. Do not create a redundant MEMORY.md.

## Recover the working memory

1. **Resolve the actual request.** Identify the app, requested platform and destination from the current instruction and valid prior instructions. Status, local install, asset preparation, draft upload, tester distribution, review submission and public release have different dependencies. Unknown authorization stays unknown; receipts, installed tools and green checks do not grant it. Reuse authorization already established in this session.
2. **Read the existing memory directly.** Use [APP.md](APP.md) for sourced product/build facts and [STATE.md](STATE.md) for checkpoints, owner decisions, limits and next actions. Read linked operation and store-section journals, including `release-output/apple-sections.md` and `release-output/google-sections.md`. Read existing CLAUDE.md, AGENT_HANDOFF.md, handoff/worklog files and relevant release/listing documents discovered elsewhere in the project; retain their valid instructions and history. Known cached evidence under appstore/work or appstore/evidence is indexed alongside release-output receipts. The helper reports their paths and fingerprints; it intentionally does not summarize private prose or logs.
3. **Reconcile identities.** Compare the intended source revision, included local changes, app identifier, platform, version/build, artifact hashes, metadata revision, locales and target device groups. A Git revision mismatch means the recorded source differs; it does not prove the older release is wrong. Determine the intended release before rebuilding. Inspect the actual changed app/build/asset paths: a harness or documentation-only commit does not automatically invalidate a binary or its captures. Git's dirty summary covers tracked files only; inspect relevant untracked app changes separately.
4. **Verify only the dependencies that matter now.** Validate the local hashes and build/signing evidence needed for the requested action. For an authorized store continuation with existing access, read the exact app/version/track, processing state, selected binary and media/copy placement before retrying a prior operation. A cached receipt is a lead for that readback, not proof of today's state. An unknown transfer outcome requires reconciliation before another upload. Use [APPLE.md](APPLE.md) or [GOOGLE-PLAY.md](GOOGLE-PLAY.md) for the relevant operation.
5. **Continue the earliest unsatisfied dependency in the requested branch.** Reuse valid builds, captures, listing copy and confirmed owner answers. A failed capture does not prevent an independently valid, authorized binary upload. Signing trouble does not prevent authorized media or copy work. A read-only status or phone install does not trigger store onboarding, a full store audit, media replacement or a public tunnel. Missing tools require setup only when the requested next step needs them; follow existing setup authorization and the project's tool-install rules.
6. **Update durable memory after actual work.** Record observed results and safe evidence links in STATE.md, updating APP.md only when a fact changes. Preserve valid owner decisions and their instruction references. Append operation intent and outcomes to the existing journal; retain unresolved waits with the exact next actor/action. Do not copy secret values, signed URLs, raw account responses or private logs into the discovery cache or public preview.

## Invalidate only affected evidence

For creative work, read the existing asset journal and current direction using [ASSET-REVISIONS.md](ASSET-REVISIONS.md). Resume the selected revision while retaining alternatives and the separate integrated revision. Record newly discovered legacy assets as baselines, not invented generation histories. For localized copy, recover the source/locale hashes, glossary/voice, reviewed edits and remaining questions from [LOCALIZATION.md](LOCALIZATION.md) and linked evidence. A fresh session must not discard a prior creative direction or retranslate reviewed copy merely because the conversation is new.

For user-supplied media, recover `release-output/inputs/index.json` and its source-to-output links using [MEDIA-INPUTS.md](MEDIA-INPUTS.md). The discovery helper inventories the index without scanning private original files. Reuse preserved uploads rather than asking for them again; if a required original is missing, report the specific missing input and continue independent work.

| New observation | Resume action |
| --- | --- |
| APP.md or STATE.md changed since adoption | Read the current file; retain the new checkpoint or decision rather than restoring the snapshot. |
| Artifact missing or its recorded size/hash differs | Stop reuse of that artifact. Repair or rebuild its branch, then update its manifest and dependent evidence. |
| Source revision changed | Identify whether the change affects the intended binary, behavior, captures or copy. Rebuild/recheck the affected outputs; keep independent evidence and owner decisions. |
| Binary rebuilt or version/build changed | Validate the new signed artifact and its identity. Previous upload/association receipts still describe the old binary. |
| Screenshot/copy changed | Revalidate only affected groups/locales/fields and read back their new placement or values after authorized writes. Do not re-upload an unchanged binary. |
| New asset candidate or direction | Append history and refresh the comparison website. A candidate or selection alone does not change the integrated app or invalidate its binary. |
| Selected artwork integrated into runtime | Verify imports/references/rendering and rebuild the affected app; record the integrated revision and mark old dependent build/capture evidence stale. |
| Marketing source, glossary or locale voice changed | Mark affected localized copy/overlays for review, preserve reviewed revisions, and regenerate only the approved locale/content scope. |
| Pending/ambiguous upload receipt exists | Read the exact remote target first. Preserve the receipt; do not blindly repeat the transfer or choose a new build number. |
| Receipt reports a past successful upload | Treat it as cached evidence; verify current processing and the intended draft/track association when store work is in scope. |
| Discovery reaches a limit or finds no target | Narrow the project directory or inspect the known target path. Do not infer that a platform is absent from an incomplete scan. |

The helper's `next_actions` are conservative discovery suggestions. They do not execute work, infer every dependency, or declare a release complete. The coordinator applies the requested scope and existing instructions to choose the next concrete action.
