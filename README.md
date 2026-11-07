# ShippyKit

Install ShippyKit into an existing iOS, Android or Unity project, then say **“Resume ShippyKit.”** Project-local skills and saved release memory let a new agent pick up builds, media, signing and store work at their current stage.

```sh
git clone --depth 1 https://github.com/jamesktan/shippykit.git ~/shippykit
~/shippykit/setup /path/to/your/app
```

With the local package already on this Mac, use `python3 ~/Documents/ShippyKit/install.py /path/to/your/app`. Installation needs Python 3.9+ and copies local files; it does not build or deploy the app. Codex skills install under `.agents/skills/` and Claude Code skills under `.claude/skills/`. Use `$shippykit` or `/shippykit`, or ask naturally. See [installation, upgrades and project memory](docs/launch/harness/README.md).

## ShippyKit: short activation

The [ShippyKit package](docs/launch/harness/README.md) includes the installer, skills, workflow and preview helper. After installing it in the app, paste:

> Use ShippyKit to resume this project's release from its saved state. Install the latest build on my phone and upload store drafts, preserving existing decisions and asking before missing-tool installation; commit and push ready changes to my personal repo's main.

The same text is saved in [ACTIVATE.txt](docs/launch/harness/ACTIVATE.txt). Replace “this project” with an app name when needed.

ShippyKit manages build uploads as part of a store-draft run. The portable [Apple uploader](docs/launch/harness/deploy/apple-upload.mjs) uploads verified IPAs and screenshots, resumes existing uploads, and reads back processing, screenshot placement and draft build selection. The portable [Google Play uploader](docs/launch/harness/deploy/play-upload.mjs) stages a verified AAB on a testing track, with listing copy and images, in one edit; it commits only when asked and reads the result back. The [Apple](docs/launch/harness/deploy/APPLE.md) and [Google Play](docs/launch/harness/deploy/GOOGLE-PLAY.md) playbooks document their commands. Reports keep builds, screenshots and copy separate: a processed build with missing screenshots is an incomplete draft.

Full store runs inspect every [App Store Connect](docs/launch/harness/deploy/APPLE-SECTIONS.md) and [Google Play Console](docs/launch/harness/deploy/GOOGLE-SECTIONS.md) section for the requested platforms. ShippyKit selects evidence-supported answers and reports its choices and reasons. If uncertain, it asks the user, applies the answer and verifies the saved value, recording decisions for resume. Draft uploads still stop before review submission or public release unless authorized.

ShippyKit also [reuses or generates app icons](docs/launch/harness/deploy/ICONS.md) when needed, integrates them into the build, and automatically creates a [local website of release assets](docs/launch/harness/deploy/PREVIEW.md). The website shows icons, screenshots, videos and public store copy; temporary ngrok sharing is offered as an opt-in. These capabilities are included in the same short activation. The bundled [image skill](docs/launch/harness/skills/shippykit-images/SKILL.md) and [store-copy skill](docs/launch/harness/skills/shippykit-store-copy/SKILL.md) also handle focused refreshes without rerunning deployment.

ShippyKit keeps [asset revision history](docs/launch/harness/deploy/ASSET-REVISIONS.md), including earlier generations, changes in visual direction and selection reasons. The review website compares versions and identifies which one is selected versus actually integrated in the app. [Marketing localization](docs/launch/harness/deploy/LOCALIZATION.md) supports natural phrasing for each audience, with optional Lingo.dev translation, glossary and brand-voice guidance.

It also uses [media you upload](docs/launch/harness/deploy/MEDIA-INPUTS.md)—photos, video, logos, audio and references—to create marketing images, clips and captioned compositions. Originals are preserved, outputs retain their source/revision links, and the review website shows prepared materials.

ShippyKit also [builds and hosts the public website](docs/launch/harness/deploy/DOMAINS.md) that store listings link to: a marketing page, support (email or a contact form), privacy policy and terms. It deploys the site on Railway through the `railway` CLI and connects your Squarespace domain. The [domain helper](docs/launch/harness/deploy/domains.py) does the work: `status` checks every step and names the single next command, `railway` adds the domain, and `squarespace` sets the DNS records and the bare-domain redirect through Cua Driver in your signed-in browser. A smaller model can run it by following the NEXT lines. ShippyKit moves the store links when the run allows store edits. Buying and renewing domains stays with you.

ShippyKit [versions every app the same way](docs/launch/harness/deploy/VERSIONING.md). Each app has one `MAJOR.MINOR.PATCH` version on every platform, starting at 1.0.0, and build numbers that only go up. Its `CHANGELOG.md` gets an entry for each user-visible change, and every entry ends with its evidence: the commit, test output or upload receipt. The [version helper](docs/launch/harness/deploy/versions.py) reads and changes the Xcode, Gradle and Unity settings, adds entries, closes a version after its upload is accepted, and prints the store "What's New" text.

Both helpers follow the same pattern so a smaller or cheaper model can run them. `status` checks everything without changing anything and ends with one `NEXT` line naming the exact command to run, a wait, an owner action, or done.

The [startup menu](docs/launch/harness/deploy/START.md) offers resume, status/setup, builds, artwork, copy/localization, versions/changelog, preview sharing, website/domain, store drafts and updates. Direct requests proceed immediately. ShippyKit checks for a newer package version once per chat and notifies you without automatically upgrading; offline checks do not block work.

## Cua Driver requirement

ShippyKit uses **Cua Driver** for automated desktop/browser setup. See [requirements and installation steps](docs/launch/harness/deploy/CUA-DRIVER.md) for supported hosts, official downloads and install locations, macOS Accessibility/Screen Recording, Windows/Linux service setup, and verification. The agent checks what exists, asks permission for a concrete installation or upgrade plan, then verifies actual window access. Builds and phone installs that already work independently can continue while GUI setup is unresolved. It also drives the Squarespace dashboard for domain DNS and forwarding ([website and domains](docs/launch/harness/deploy/DOMAINS.md)).

## Start here: paste into Codex Astra

Open Codex Astra in the project you want to ship and paste the block below. The same text applies to existing iOS, Android, and Unity projects. Astra discovers the project's build system and uses the tools available there. This entry point requires no account, hosted service, plugin installation, or changes to the project's architecture.

```text
Prepare this project for its app-store launch. Assume the product is ready to deploy. Work directly in this repository and use its existing build system. Complete the work; do not stop at a plan or create a separate platform.

STEP 1 — BUILD AND PREPARE THE STORE ASSETS. Do this now.

Inspect the project to identify its app name, supported platforms, build targets, app identifiers, existing signing configuration, and how to run it. Support the platforms this project actually contains, whether native iOS/Android, Unity, or another framework. Read its code, README, UI, and existing assets to understand its audience, main benefit, and strongest real features. Infer routine choices. Ask only for information or access that genuinely blocks the work, and continue independent tasks meanwhile.

1. Inspect and validate the app icons. Reuse valid branding; generate and integrate missing/placeholder artwork when needed using the ShippyKit icon workflow at https://github.com/jamesktan/shippykit/blob/main/docs/launch/harness/deploy/ICONS.md. Save the master and platform exports under release-output/icons/. Then build it using the existing toolchain. Fix small build/configuration blockers. Produce the release archive/package supported by this environment and a runnable build for capture. Reuse existing signing if available; record unresolved signing for step 2. Keep capture/debug instrumentation out of the release build. Do not redesign the app or add unrelated features.

2. Run the app in an appropriate simulator, emulator, or device. Exercise its main user journeys and capture actual screenshots and video showing its strongest features. For Unity, use its existing scenes and build targets. Use existing safe demo/test data. Capture clean originals and make store-ready images and short videos with readable, persuasive text overlays. Use real app footage and accurate claims. Verify current official Apple/Google media requirements for the supported targets; export the required sizes and encodings. Keep any promotional variants that do not meet store rules separate.

3. Write compelling, accurate store copy grounded in this project. Save Markdown with the relevant title/name, subtitle or short description, full description, feature/benefit bullets, keywords where supported, and release notes. Put missing policy/support URLs or declarations that cannot be verified into a short needs-input file; do not invent them.

4. Save everything under release-output/ in this project:
   - builds/ios/ and builds/android/: available release artifacts.
   - icons/: icon master and platform/store exports.
   - captures/: original screenshots and footage.
   - stores/ios/ and stores/android/: upload-ready screenshots, videos, and listing.md, organized by locale and required device size.
   - promo/: optional promotional media.
   - site/: the automatically generated local asset-preview website.
   - manifest.json: relative file paths, public asset kinds, SHA-256 hashes, platform, locale, dimensions, encoding, duration where relevant, and build/version identifiers.
   - README.md: actual build/capture commands, what was produced, and any remaining blockers.
   - needs-input.md: only unresolved facts or access needed for launch.
   Create only the platform folders that apply. Keep credentials out of these files.

5. Generate the local website with the ShippyKit preview helper following https://github.com/jamesktan/shippykit/blob/main/docs/launch/harness/deploy/PREVIEW.md, copying the helper into deploy/ if needed. Include only selected public media and sanitized copy. Verify it and offer an optional temporary ngrok link; wait for explicit opt-in before exposing it and obtain permission before any missing-tool install. Inspect the exported images and videos, verify dimensions/encoding and file existence, and check the release build outcome. Never substitute placeholders for captures or claim a failed build succeeded. Finish with the output-folder path, a short list of completed deliverables, and any concrete blockers.

STEP 2 — SIGNING AND STORE UPLOAD. Wait until I ask for step 2.

Reuse release-output/ and its manifest. Require Cua Driver for desktop/browser setup: inspect it, obtain permission for missing installation or upgrades, guide OS permissions, and verify a real window before GUI work. Follow https://github.com/jamesktan/shippykit/blob/main/docs/launch/harness/deploy/CUA-DRIVER.md. Use it with my available signed-in Apple/Google accounts to configure app records, certificates, provisioning profiles, signing, and required store settings. Reuse valid signing assets; do not revoke working certificates. Use native build/upload tools where they make the job faster. Ask me only for unavoidable login/MFA, missing account access, legal declarations, or charges. Then build/sign as needed and upload the binary, copy, screenshots, videos, and other supported assets. Save the resulting app/build identifiers, console links, and upload status. Leave the submission as a draft; submit for review or release publicly only when I explicitly request it.
```

When the assets are ready, the follow-up is simply: **“Do step 2 using `release-output/`.”** A project still needs its platform toolchain and store access for the steps that use them; Astra should report the specific blocker if either is unavailable.

The [launch and porting workflows](docs/launch/README.md) now codify Apple onboarding through release, with a reusable deployment prompt, configuration template, and local preflight. They also include a [Codex-assisted iOS ↔ Android porting structure](docs/launch/mobile-porting.md) and [paste-in porting prompt](docs/launch/prompts/port-mobile-app.txt). The porting structure is a draft; it does not claim an Android implementation exists.

To keep deployment instructions and progress inside any app repository, use [ShippyKit](docs/launch/harness/README.md). It sets up the `deploy/` folder and includes phone installation, Apple and Google Play procedures, and a resumable deployment log.

## Tests

The tests need Python 3.9+ and Node 18+; they use only the standard libraries.

```sh
python3 -m unittest discover -s tools -p 'test_*.py'
node --test tools/test_shippykit_apple_upload.mjs tools/test_shippykit_play_upload.mjs
```

The uploader tests exercise upload/retry and readback behavior with simulated Apple and Google Play responses; live store verification is recorded separately in each app's release evidence. The domain helper tests drive a simulated Squarespace dashboard and simulated Railway, DNS and HTTP answers. The version helper tests use throwaway Xcode, Gradle and Unity projects.

## License

ShippyKit is available under the [MIT License](LICENSE). The package keeps its own copy in [docs/launch/harness/LICENSE](docs/launch/harness/LICENSE), which the installer copies into each app as `deploy/LICENSE`. It covers ShippyKit's files, not the app's own code.
