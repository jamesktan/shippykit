# Codex-assisted iOS ↔ Android porting

This is a proposed repository workflow and a [reusable execution prompt](prompts/port-mobile-app.txt). It does not implement a converter or an Android version of Isofall. Codex can inspect a working app, extract its behavior, implement the other platform, and compare both against the same fixtures. The result is maintainable target source, its native build, and evidence of parity.

Use this workflow in the app's repository. It requires no hosted service or account. For a future port, paste the execution prompt into Codex with the source project open. For a planning request, produce the inventory, contract, mappings, and work plan first; do not start the target implementation.

## Choose the smallest appropriate implementation

| Existing project | Default target approach |
|---|---|
| Native iOS app | Kotlin with Jetpack Compose for a new Android UI, plus target implementations of the existing behavior and platform services. |
| Native Android app | Swift with SwiftUI for a new iOS UI, plus target implementations of the existing behavior and platform services. |
| Existing Flutter, React Native, Kotlin Multiplatform, Unity, Godot, or other shared stack | Preserve its architecture and extend its existing platform target; identify unsupported plugins and native adapters first. |
| Native game or custom renderer | Port deterministic rules first. Run a bounded target renderer spike before committing to the rendering implementation. Preserve existing reusable C/C++ or other portable libraries where practical. |
| Both mobile apps already exist | Compare and fill the requested platform's gaps. Do not generate a third app. |

These are workflow defaults, not a language transpilation guarantee. Map product behavior and visual intent rather than translating SwiftUI, SceneKit, Compose, or Android Views line by line. Keep the source app working and retain its brand, interaction intent, content, and timing. Adapt navigation, system back, safe areas, window sizes, text scaling, accessibility, and permission prompts to the target platform. See [SwiftUI app organization](https://developer.apple.com/documentation/swiftui/app-organization) and [Compose adaptive layouts](https://developer.android.com/develop/ui/compose/layouts/adaptive/get-started-with-adaptive-apps).

For Unity, reuse scenes, scripts, assets, and the project's installed editor version. Add or repair the mobile build profile and platform plugins; audit platform-specific defines, input, shaders, textures, audio, and SDKs. Build profiles provide platform-specific build configuration; they do not establish feature or device parity. Follow the documentation for the project's Unity version, such as [Unity 6 build profiles](https://docs.unity3d.com/6000.0/Documentation/Manual/build-profiles.html). Do not upgrade the engine or replace a working shared stack merely to perform a port.

Infer routine choices from the repository. Ask the owner only when a missing fact or a material product decision blocks a feature: inaccessible source, an unavailable license, a required platform-exclusive capability without an acceptable equivalent, account entitlement policy, or an unknown target when the request cannot determine it. Continue independent work and record the exact blocked feature. A routine architecture decision is not a platform-selection questionnaire.

## Repository output

Keep existing source directories in place. Create only the missing target, using the repository's established layout. For a project without a convention, `android/` or `ios/` is a reasonable target root. Shared-stack projects retain their own target layout.

```text
<app repository>/
  <existing source app>/           # unchanged product baseline
  android/ OR ios/                 # missing native target, with its own build/tests
  porting/
    manifest.json                 # direction, source revision, target path, contract version
    inventory/
      source.json                 # targets, versions, commands, dependencies, capabilities
      journeys.md                 # screens, actions, states, failures, accessibility
      assets.csv                  # source paths, hashes, license/provenance, reuse decision
    behavior/
      contract.md                 # platform-neutral rules and observable outcomes
      fixture.schema.json         # portable action/state/effect representation
    mappings/
      platforms.md                # source → intent → target API → verification
      dependencies.md             # reuse/replace/unavailable, versions, licenses
    fixtures/semantic/            # source-derived inputs and expected results
    runners/                     # source/target fixture commands and comparison adapter
    evidence/<run-id>/
      source/                    # build logs, baseline captures, semantic output
      target/                    # build logs, actual target captures, semantic output
      parity.json                # per-check status and paths to evidence
    decisions.md                 # approved adaptations and unresolved blockers
    work-plan.md                 # owners, file boundaries, dependencies, completion gates
  release-output/                 # existing launch workflow's builds and store deliverables
```

`manifest.json` records `schemaVersion`, `direction`, `sourceRevision`, source dirty-file hashes if applicable, `sourcePath`, `targetPath`, `contractVersion`, toolchain versions, and exact commands. Do not duplicate source trees into an unmaintained snapshot. Reference the baseline revision and keep reproducible evidence. Store no credentials, production account data, signing secrets, or bearer tokens in these files.

## Execution stages and gates

| Stage | Concrete work | Required result |
|---|---|---|
| 1. Establish the source | Read local instructions; inspect build targets and code; build and run the source; exercise its principal journeys. Record dependency locks, identifiers, minimum OS versions, environments, permissions, storage, services, assets, and existing tests. | Source revision, reproducible commands, and real baseline captures. An unavailable source toolchain is recorded as blocked evidence, not a successful baseline. |
| 2. Freeze behavior | Define inputs, transitions, outputs, error states, persistence, clocks, random numbers, background behavior, and external effects. Extract portable fixtures from the source implementation and corroborate them with existing tests and product intent. | Versioned contract, expected outcomes, platform mapping, and an explicit list of discrepancies. Do not silently freeze an identified source bug as desired behavior. |
| 3. Prove target core | Create the smallest buildable target. Implement domain logic and fixture adapters, with injected clocks, randomness, storage, and service fakes. Preserve the existing backend contract. | Source and target produce matching semantic outputs before the complete target UI is built. A renderer spike may run in parallel, isolated from production UI. |
| 4. Integrate native surfaces | Build target navigation, UI, accessibility, platform services, rendering, audio, and asset packaging. Implement the agreed mappings. | Main journeys work on the target; unsupported capabilities are visible in the parity report. |
| 5. Verify both apps | Rerun source regressions and target tests. Compare deterministic state; test real UI, lifecycle, device APIs, timing, and audio separately. | Evidence tied to the same contract, source revision, target revision, binary, and test environment. Required blocked or untested checks prevent a complete parity verdict. |
| 6. Prepare launch | Produce runnable and release builds, actual captures, platform-specific listing copy, and store media. | The existing `release-output/` handoff is complete for the verified platform. Signing, upload, review submission, and public release retain their existing authorization boundaries. |

The baseline app should remain usable throughout. A small source-side fixture exporter or dependency-injection seam can be justified, but avoid a source UI rewrite. Review those source changes independently and rerun its regressions. Once both platforms are maintained, make future behavior changes in the shared contract and fixtures first, then implement both sides. Reversing the port direction means using the other app as the baseline; it does not mean mechanically round-tripping generated source or overwriting local changes.

## Parallel ownership

The coordinator owns the manifest, contract version, work plan, cross-platform decisions, dependency locks, root build configuration, integration, and final verdict. Freeze interfaces before handing files to workers.

| Worker | Exclusive files or responsibility | Dependency |
|---|---|---|
| Source/contract | Source inventory and fixture exporter; proposed contract and reference fixtures | Baseline access; coordinator accepts contract changes |
| Target core | Target domain code and semantic test runner | Frozen fixture schema and behavior contract |
| Platform adapters | Target persistence, auth, permissions, billing, notifications, lifecycle, audio | Frozen ports; target UI consumes these interfaces |
| UI/renderer | Target screens, resources, renderer spike and implementation | Domain/API contract; complete UI follows core parity |
| Verification/release | Cross-platform comparison, journey tests, capture and release evidence | Runnable builds; source expected outcomes remain independently owned |

Assign literal paths in `work-plan.md`, not overlapping areas such as “all Android code.” Use fewer workers when files cannot be separated. Workers report changed files, commands, evidence paths, and unresolved gaps. Contract changes go through the coordinator; a worker must not weaken an expected outcome to make its own port pass. Serialize simulator ownership, large builds, engine imports, and signing operations even while independent code work runs in parallel.

## Map platform capabilities explicitly

Each mapping records the source behavior, target implementation, observable acceptance test, and status: equivalent, adapted, blocked, or not applicable. The following are investigation categories, not automatic API substitutions.

| Capability | Porting requirements |
|---|---|
| UI, navigation, accessibility | Preserve tasks and hierarchy; implement native navigation/back behavior, focus, keyboard, insets, text scaling, localization, and screen-reader labels. Test compact and larger windows supported by the product. |
| Permissions and device features | Inventory entitlements, usage strings, manifest entries, and runtime requests. Request only capabilities needed by an existing feature; test denied, restricted, revoked, and unavailable-device states. Android permissions include a separate runtime flow: [official guide](https://developer.android.com/training/permissions/requesting). |
| Data and secure storage | Preserve schema, migrations, validation, time zones, deletion, backup, and offline behavior. Map ordinary preferences, databases, files, and protected credentials separately. Do not promise that local iOS data or keys automatically move to Android; cross-device migration requires an existing sync/export path or an explicit product decision. |
| Authentication | Preserve backend user identity, authorization, session expiry, refresh, logout, account deletion, and recovery. Configure target-specific provider client identifiers and callbacks; never copy a source token into a new platform to simulate login. Credential UI may use [Android Credential Manager](https://developer.android.com/identity/credential-manager), but account linking remains a backend/product contract. |
| Purchases | Map the product catalog, entitlement state machine, restore, pending purchases, cancellation, refunds, and subscription changes. StoreKit transactions and Play purchase tokens require their respective verification paths; do not assume purchases transfer between stores. Reuse an existing verified account-entitlement backend where present. Use platform test environments: [StoreKit](https://developer.apple.com/storekit/) and [Play Billing](https://developer.android.com/google/play/billing/integrate). |
| Background execution | Define required outcomes and deadlines, then select permitted target mechanisms. Test suspension, termination, retries, duplicates, and battery restrictions. A foreground timer does not imply an always-running background service. See [Android background task selection](https://developer.android.com/develop/background-work/background-tasks). |
| Links and notifications | Preserve route semantics, validation, cold/warm launch behavior, deduplication, notification opt-out, and expired sessions. Configure each platform's association files and push credentials/token registration independently. [Apple universal links](https://developer.apple.com/documentation/xcode/supporting-universal-links-in-your-app) and [Android links](https://developer.android.com/training/app-links) need platform-specific routing setup. |
| Backend and network | Reuse endpoints, schemas, error meanings, pagination, retry/idempotency rules, and authorization. Preserve offline-first behavior where present. Use test accounts or recorded/synthetic responses for destructive cases; backend changes require a separate owned contract change. |
| Graphics, media, sound, haptics | Preserve visual intent, coordinate systems, timing, event-to-sound mapping, mute preference, overlapping voices, interruptions, and resource cleanup. Device APIs are separate adapters. Android [SoundPool](https://developer.android.com/reference/android/media/SoundPool) supports short effects with a bounded stream count; [audio focus](https://developer.android.com/media/optimize/audio-focus) still needs its own lifecycle policy. |
| Dependencies, licenses, assets | Audit SDK target support, native binaries, tracking/data collection, transitive dependencies, asset and font redistribution rights, attribution, codecs, density, and localization. Reuse permitted original assets with hashes; record any conversion. A platform-exclusive SDK needs a documented replacement or a blocker, not a fabricated equivalent. |

For platform-exclusive features such as a particular health service, cloud container, wearable extension, or game-service identity, propose the smallest product-equivalent alternative and its limitations. Escalate only decisions that change user-visible promises, data ownership, costs, licensing, or access. A denied permission or unavailable device feature is usually a state to handle and test, not a reason to stop unrelated porting work.

## Deterministic parity before UI polish

Semantic fixtures specify an initial state, seed, virtual clock, ordered actions, service responses, and expected state/effects after each meaningful step. Generate expected results through the source harness; independently check critical invariants. Run the same fixture files through the target harness. Compare state and events, not source language implementation details.

Pin integer widths, signedness, overflow, random-number algorithm and consumption order, sorting, rounding, serialization, locale, units, and time resolution. Encode 64-bit seeds/state as hexadecimal or decimal strings where JSON number precision would lose information. Specify floating-point tolerances only for quantities that require them; exact game rules, identifiers, money, and entitlement states should not acquire arbitrary tolerances. Include invalid inputs, boundaries, interruption/resume, migration, and repeated actions.

`parity.json` records each requirement and fixture ID with `pass`, `fail`, `blocked`, or `not_run`, source/target outputs, differences, commands, revisions, toolchain/device versions, and evidence paths. A missing source result, skipped target test, or mock-only platform integration cannot produce a complete pass. Fix or explicitly resolve discrepancies; do not regenerate reference results from the target implementation.

After core parity, verify actual UI separately: cold first frame, navigation/back, input, accessibility, text scaling, app background/foreground, process recreation where applicable, save/restore, offline/error states, audio, and representative device sizes. Compare matching journey states and brand intent, allowing documented platform adaptations. Pixel equality across native platforms is not the acceptance criterion. Detect blank scenes and missing assets; inspect the actual screenshots and listen to actual audio recordings. A screenshot alone cannot verify sound.

## Isofall worked plan — no Android implementation yet

The source example is the native SwiftUI/SceneKit Isofall app. Its current source has these requirements; the eventual port must pin an exact revision and generate fixtures from that revision rather than treating this document as an executable oracle.

| Preserve | Concrete acceptance coverage |
|---|---|
| 8×8×10 well | Floor is 64 cells, coordinates are centered consistently, floor is `y = 0`, complete layers require 64 cells, spawn and game-over behavior match. Preserve the six regular piece shapes and their rotation/wall-kick rules from `GameEngine.swift`. |
| Piece generation | SplitMix64 with wrapping unsigned 64-bit arithmetic, rejection sampling, exact draw order, seed zero, restart semantics, and an independent six-piece bag. The combined special probability is 35% per draw; it is not 35% per kind or an exact quota in each short run. Compare exact long seeded sequences and separately audit the probability rule. |
| Three single-cube specials | Plane eraser clears `max(0, landing.y - 1)`. Blast uses offsets `-3...4` on each axis, clipped to the well, forming an 8×8×8 region before clipping. Color eraser removes the selected color across the board; Spin cycles its six target colors. Specials disappear on impact; column compaction precedes ordinary full-layer clearing. |
| Six colors and effects | Teal, coral, lavender, cream, blue, and rose retain their stable indices and target meaning. Preserve special markers, ghost behavior, scoring, level progression, drop timing, pause/restart, and settings. Export fixtures for edge blasts, empty effects, compaction, multiple layer clears, color cycling, and game-over. |
| Existing sound assets | Reuse the original ten WAV effects after verifying provenance and hashes. Preserve action triggers, successful-action filtering, per-effect throttles, four-voice cap, sound-off, pause/game-over stopping, and interruption/background cleanup. Verify the target's audio device and focus behavior with actual playback. |
| Offline product | Keep gameplay offline. Do not add accounts, networking, analytics, ads, purchases, or a backend to make the port easier. Preserve local preferences and score semantics. |

The default Android implementation plan is a pure Kotlin rules module and a Compose app shell. Before the full UI, build an isolated renderer spike using the simplest suitable Android rendering implementation already available to the project. Prove a real isometric 8×8×10 scene, all six colors, distinct special markers, translucent ghosts, correct occlusion, camera fit and turns, reliable cold first frame, and acceptable idle/active rendering behavior. Replace the SceneKit rendering adapter; do not rewrite the game in Unity merely to avoid this spike or substitute a flat mock screenshot for the actual scene.

For sound, carry the WAVs and behavioral event contract across, but adapt playback to the target. Isofall's iOS implementation uses an [ambient session](https://developer.apple.com/documentation/avfaudio/avaudiosession/category-swift.struct/ambient) that mixes with other audio and respects the Silent switch. Android media volume, ringer state, and audio focus are different mechanisms; document and test the closest non-disruptive target policy without claiming identical hardware-switch behavior. Keep the in-app mute control authoritative and stop short effects when leaving the foreground.

First target milestones are: exact core fixture parity; renderer spike; one complete play/pause/restart journey with sound; then the full UI and release evidence. This draft creates none of those target deliverables.

## Release handoff

Use the existing [universal launch prompt](../../README.md#start-here-paste-into-codex-astra) after target parity. It builds and captures the platforms the project actually contains. Produce independent `release-output/builds/ios/` and/or `builds/android/`, original captures, platform/locale store images and video, listing copy, `manifest.json`, actual commands, and `needs-input.md`. Verify current official store requirements when exporting. Never relabel an iOS capture as Android, or reuse a source-only feature claim in target store copy.

For iOS, follow [Apple deployment](apple-deployment.md) and its [execution prompt](prompts/deploy-apple.txt). Use the documented `tools/apple-preflight.py` invocation and `apple-release.example.json` configuration to produce `release-output/apple-preflight.json`; retain any blockers. A simulator build is capture evidence, not a signed distributable. For Android, produce a runnable APK and the intended release artifact when the target toolchain and signing permit, recording missing access honestly. Keep capture hooks and fixture-only controls out of release builds.

Preparation does not authorize store upload or public release. The existing launch prompt reserves signing/store upload for the user's step 2 request and leaves the submission as a draft; review submission or public release needs the user's explicit instruction. The final handoff distinguishes implemented parity, untested platform behavior, build/capture evidence, signing readiness, and store status.

Platform references above were checked on 2026-10-23. Recheck relevant official APIs and store requirements against the app's actual SDK and target OS versions when executing a port.
