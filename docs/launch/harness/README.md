# ShippyKit

ShippyKit is an installable set of project-local skills and deployment tools for an existing iOS, Android, or Unity app. Install it at any stage: a new app, an existing release pipeline, or a partially uploaded store draft. It reads the project's existing history and continues the requested work from the next unfinished step.

## Install into a project

With this package at `~/Documents/ShippyKit/`, run from the app repository:

```sh
python3 ~/Documents/ShippyKit/install.py .
```

The installer uses Python 3.9+ with no third-party dependencies. It installs `shippykit`, `shippykit-images` and `shippykit-store-copy` into the project's `.agents/skills/` for Codex and `.claude/skills/` for Claude Code, copies the `deploy/` tools/guides, and adds pointers to the project's instructions. Use `--agent codex` or `--agent claude` to select one, or `--dry-run` to inspect the changes first. No app build, store mutation, tunnel or tool download occurs during installation.

From a Git checkout, use the root `setup` command:

```sh
git clone --depth 1 https://github.com/jamesktan/shippykit.git ~/shippykit
~/shippykit/setup /path/to/your/app
```

Install again to upgrade. Files unchanged since their last managed installation update automatically; customized or unrecognized files stay in place with new candidates under `.shippykit/incoming/` for the agent to merge. Existing `deploy/APP.md`, `deploy/STATE.md`, release assets, other skills and unrelated instructions are preserved. The portable receipt at `.shippykit/install.json` records the package version and owned file hashes. It is safe to commit the installed guides, skills, receipt and sanitized project memory with the app.

## Activate

After installation, say **“Run ShippyKit”** or **“Resume ShippyKit.”** In Codex, invoke **`$shippykit`**; in Claude Code, use **`/shippykit`**. A new session may be needed for skill discovery to refresh; the agent can read the installed SKILL.md directly meanwhile. For the original phone-and-drafts workflow, use the [short activation](ACTIVATE.txt):

> Use ShippyKit to resume this project's release from its saved state. Install the latest build on my phone and upload store drafts, preserving existing decisions and asking before missing-tool installation; commit and push ready changes to my personal repo's main.

For an app without an installation, tell the agent to install ShippyKit from this package first. A new deploy/upload request defaults to drafts; resume retains the prior requested destination and permissions unless the user changes them. A status question stays read-only. Review submission and public release need the user's actual instruction.

On entry, ShippyKit follows [START.md](deploy/START.md): it checks for a newer package version, gives a brief update notice when available, and offers a short menu when no task was specified. Choose **Resume**, **Status & setup**, **Build & install**, **Artwork & revisions**, **Store copy & localization**, **Preview & share**, **Store drafts**, or **Update ShippyKit**. A direct request already chooses the route, so work proceeds without another menu question. Checks run once per chat; an offline check does not block work, and a notice does not update files automatically.

You can also check explicitly with `python3 deploy/shippykit.py updates --project .`. It reads the installed receipt and the official repository's latest package version; a private repository can use an existing authenticated GitHub CLI. It does not log in or install tools, and ordinary `status` remains offline. Follow START.md to update the package and run the preserving installer when an upgrade is requested.

## Memory and adoption

Follow [RESUME.md](deploy/RESUME.md). The memory travels with the project, so switching agents or opening a new window does not reset the release:

| File | Purpose |
| --- | --- |
| `deploy/APP.md` | Stable app/build facts, platform choices, owner decisions and secure credential references |
| `deploy/STATE.md` | Checkpoints, evidence, blockers, permissions and the exact next action |
| `release-output/*-sections.md` | Store selections, rationale, owner answers and verified saved values |
| `release-output/artwork/revisions.json` | Asset generations, visual directions, selections and actual integration evidence |
| `release-output/inputs/index.json` | Preserved user uploads, intended roles, inspection and links to marketing outputs |
| `.shippykit/install.json` | Installed version and hashes for safe updates |
| `.shippykit/discovery.json` | Optional ignored local discovery cache; never proof of deployment completion |

Inspect or adopt an existing project without building or uploading:

```sh
python3 deploy/shippykit.py status --project .
python3 deploy/shippykit.py adopt --project .
```

`status` reads local evidence without writes; `adopt` saves the discovery cache without overwriting app facts or progress. Add `--json` for structured output and `--verify-hashes` to check available manifest artifacts within the helper's size limits. The agent reconciles existing release/handoff documents and dated receipts, verifies the relevant current local/remote state, and continues only unfinished work. Another tool's pipeline remains usable; existing store drafts are not recreated merely because ShippyKit was installed later.

A draft upload includes separate evidence for binary transfer and processing, the selected draft build/track, placed screenshots and other requested media, and saved factual copy. Missing requested screenshots keep the run incomplete even when the build upload succeeds. Continue independent work: capture problems need not block a valid build upload, and signing problems need not block authorized media/copy uploads. Reuse existing permissions and record each remaining dependency.

Full store runs also read every actual [App Store Connect](deploy/APPLE-SECTIONS.md) or [Google Play Console](deploy/GOOGLE-SECTIONS.md) section, including conditional forms. ShippyKit chooses supported answers automatically and tells the user what it chose and why. When uncertain, it asks, applies the answer and verifies the saved value. Internal Markdown journals preserve the choices and remaining questions for resume. Checking the sections does not authorize review submission or public release.

ShippyKit first discovers the app's existing targets and setup. For an iOS-only app it asks whether to add Android; for an Android-only app it asks whether to add iOS. If the user opts in, it checks that environment, lists what is missing, and presents the installation and app-development plan for permission before acting autonomously. It reuses platform choices and specific permissions already given. Missing prerequisites come with concrete next steps before dependent deployment work starts.

## Icons and release preview

ShippyKit checks the app icon before the final build: reuse working branding, or generate missing/placeholder artwork and export the actual iOS, Android or Unity assets using [the icon workflow](deploy/ICONS.md). It automatically builds a [local preview website](deploy/PREVIEW.md) with icons, screenshots, videos and public store copy. It offers a temporary ngrok link after local verification; public sharing and any missing-tool installation need the applicable permission. The standard activation above includes these steps during asset preparation, without a longer prompt.

## Reusable creative skills

The package includes [shippykit-images](skills/shippykit-images/SKILL.md) for app artwork, icons and store image compositions, and [shippykit-store-copy](skills/shippykit-store-copy/SKILL.md) for new or refreshed listing text. Full runs use them during asset preparation. A focused request uses only the relevant skill and preserves existing app state, locales and unrelated work. Both update the release manifest and local preview when their public outputs change.

The [asset revision workflow](deploy/ASSET-REVISIONS.md) preserves each generation and change of direction. The website groups revisions by asset for visual comparison, shows decision history, and distinguishes the selected candidate from the version actually integrated into the app. Original masters and generation prompts remain in the project's private evidence; only explicit review exports and safe summaries enter the website.

[User-uploaded media](deploy/MEDIA-INPUTS.md) can supply photos, videos, logos, audio, screenshots and brand references for marketing materials. ShippyKit preserves originals, records their intended role, creates the requested edits/compositions and captions, and links each output to its inputs and revision history. The review website displays the prepared exports; raw uploads stay private. For example: **“Use these uploaded photos and clips to make marketing images and a short promo video for this app.”**

[Marketing localization](deploy/LOCALIZATION.md) adapts copy and screenshot overlays to each locale's audience, voice and terminology while preserving verified product facts. Lingo.dev is an optional provider for translation and naturalization with an existing engine, glossary and locale voice. The guide covers setup, version differences, narrow content scope, reviewed edits and validation. Using it does not add app UI language support; installation, paid service usage and new locale scope follow the user's permissions.

After bootstrap, examples are **“Use $shippykit-images to create new promotional images for this app”** and **“Use $shippykit-store-copy to update the English listing for the latest features.”** Before bootstrap, say **“Use ShippyKit at ~/Documents/ShippyKit/ to refresh this app’s images and store copy.”** This does not imply a store upload or full deployment.

## Required desktop setup: Cua Driver

[Cua Driver requirements and installation](deploy/CUA-DRIVER.md) are part of onboarding. For automated desktop/browser setup, the agent must verify the driver, daemon, OS permissions and access to the intended window. If anything is missing, it presents a concrete installation plan and asks permission before installing or upgrading. The guide includes macOS/Linux and Windows commands, install paths, macOS Accessibility/Screen Recording steps, startup options and verification. Existing builds, API/CLI work and phone installs can continue independently.

## Agent installation and bootstrap

For an image/copy-only request, read the relevant packaged skill directly and copy its skill folder plus only the supporting guides/helper it needs. The full sequence below is for a deployment run; a focused refresh does not need a new deployment scaffold.

1. Resolve the actual app repository from the user's window/request and read its instructions. Keep the package source separate; do not install into a parent folder merely because it has the app's name.
2. Run `python3 /path/to/ShippyKit/install.py /path/to/app` with the requested agent selection. This is a local file installation, not permission to install missing OS/toolchain dependencies or start deployment. If Python is unavailable, follow the existing concrete setup permission check. Never reuse another app's filled APP.md or STATE.md.
3. Inspect the install report. Merge relevant candidates in `.shippykit/incoming/` with any customized workflow; preserve project facts, progress and local rules. Re-run the installer after merging to reconcile owned files. Do not remove unrelated skills or instructions. Skill locations follow [Codex project skills](https://learn.chatgpt.com/docs/build-skills#where-codex-loads-local-skills) and [Claude Code skills](https://code.claude.com/docs/en/skills).
4. Read the installed core `shippykit/SKILL.md` and `deploy/RESUME.md`. Inspect the current state, existing non-ShippyKit handoffs and release evidence before choosing a starting point. For install-only requests, stop after installation/adoption and report the next action.
5. For an authorized deployment, follow `deploy/README.md` within the requested scope. Infer APP.md from the real project and record decisions, readiness evidence and the next action in STATE.md. Keep per-app facts and outputs in that app, not this reusable package. Focused image/copy tasks still use only the relevant skill and supporting guides.

Use installed platform tools and authorized store access. No hosted ShippyKit service is needed. Honor the selected personal repository and existing commit/push instructions; verify the remote owner before pushing.

```text
<app repository>/
  AGENTS.md                 # optional pointer merged into existing instructions
  CLAUDE.md                 # preserved instructions plus Claude skill pointer, if selected
  .shippykit/
    install.json            # portable package version and managed file hashes
    discovery.json          # optional ignored local evidence inventory
    incoming/               # ignored upgrade candidates for customized files
  .agents/skills/
    shippykit/              # discover existing work and resume the requested release
    shippykit-images/        # app artwork, icons and truthful store imagery
    shippykit-store-copy/    # grounded listing updates with locale/field validation
  .claude/skills/            # same skills for Claude Code, if selected
  deploy/
    LICENSE                 # ShippyKit's MIT license; the app's own code keeps its license
    README.md               # coordinator: execute the requested stage, resume safely
    RESUME.md               # adopt existing pipelines and reconcile saved evidence
    START.md                # first-chat menu, update notice and preserving upgrade route
    shippykit.py            # local status/adoption and explicit remote version check
    APP.md                  # inferred app/build facts, credential references, decisions
    APPLE.md                # Apple onboarding, signing, upload, review and release
    APPLE-SECTIONS.md       # inspect Apple sections, select/report answers, resolve uncertainty
    apple-upload.mjs         # optional Apple API/native upload helper; see APPLE.md
    GOOGLE-PLAY.md          # Play onboarding, signing, tracks, review and publication
    GOOGLE-SECTIONS.md      # inspect Play sections, select/report answers, resolve uncertainty
    play-upload.mjs         # optional Play API upload helper; see GOOGLE-PLAY.md
    CUA-DRIVER.md           # required GUI driver: prerequisites, install, permissions, verify
    DOMAINS.md              # build public site, host on Railway, Squarespace DNS/forwarding via Cua Driver
    domains.py              # domain helper: status says the next step; railway/squarespace apply it
    VERSIONING.md           # MAJOR.MINOR.PATCH everywhere, rising builds, evidence-backed CHANGELOG.md
    versions.py             # version helper: status, note, set, release, store notes
    ICONS.md                # reuse or generate icons, integrate and validate each target
    ASSET-REVISIONS.md      # preserve generations/directions and compare selected/integrated art
    MEDIA-INPUTS.md         # inspect/preserve user uploads and turn them into marketing assets
    LOCALIZATION.md         # natural marketing copy and optional Lingo.dev workflow
    PREVIEW.md              # automatic asset website and opt-in temporary sharing
    preview.py              # dependency-free static gallery builder and loopback server
    STATE.md                # observed status, receipts, blockers, next action
  release-output/           # generated builds, actual captures, copy and evidence
```

For assets only, ask ShippyKit to prepare builds and store assets without uploading. For phone-only deployment, ask it to install and launch on the connected phone. Store access must not prevent independent local builds, capture, or an installation supported by existing development signing.

The files contain instructions and durable context. Codex executes the work with Xcode/Gradle/Unity, capture/media tools, store APIs/CLIs, and browser/desktop control. Membership, authentication, factual declarations, signing keys, and store review cannot be supplied by Markdown. The agent infers routine facts and requests only missing information that actually prevents progress.

Extended references: [Apple runbook](https://github.com/jamesktan/shippykit/blob/main/docs/launch/apple-deployment.md), [launch workflow](https://github.com/jamesktan/shippykit/blob/main/docs/launch/README.md), and [optional mobile porting](https://github.com/jamesktan/shippykit/blob/main/docs/launch/mobile-porting.md). The local deployment files contain the deployment procedure; these references supply additional context. A deployment request or interest in another platform alone does not authorize autonomous installation or porting.
