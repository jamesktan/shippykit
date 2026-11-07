# Launch and port an existing mobile app

These are reusable Codex workflows for a project that is ready to ship. Start in that app's repository; Codex uses its existing build tools and available API, browser, and desktop tools.

For the short entry point, use [ShippyKit](harness/README.md) and its [short activation](harness/ACTIVATE.txt). The agent installs the `deploy/` harness into the app, fills in project facts, and maintains resumable state. The local package lives at `~/Documents/ShippyKit/`.

The [preview verification record](examples/shippykit-preview-verification.md) includes the helper regression command and checks against Isofall's actual release assets.

| Task | Paste into Codex | Supporting instructions |
| --- | --- | --- |
| Build, capture, and prepare store copy/media | [Universal launch prompt](../../README.md#start-here-paste-into-codex-astra) | Produces `release-output/`; works with the platforms actually present |
| Generate or refresh app/store imagery | `Use $shippykit-images` after bootstrap | [Image skill](harness/skills/shippykit-images/SKILL.md); actual captures remain the source for screenshots |
| Update localized store copy | `Use $shippykit-store-copy` after bootstrap | [Copy skill](harness/skills/shippykit-store-copy/SKILL.md); grounded changes, field limits and local preview |
| Reuse or generate app icons | Included in ShippyKit asset preparation | [Icon workflow](harness/deploy/ICONS.md); integrates target assets before the final build |
| Generate an asset website and optionally share it | Included in ShippyKit asset preparation | [Local preview and ngrok](harness/deploy/PREVIEW.md); public sharing is opt-in |
| Keep versions, build numbers and the changelog consistent | `Versions & changelog` in the ShippyKit menu | [Versioning](harness/deploy/VERSIONING.md); `versions.py status` names each next step |
| Build the public support/privacy site and connect a custom domain | `Website & domain` in the ShippyKit menu | [Website, Railway and Squarespace](harness/deploy/DOMAINS.md); Squarespace DNS through Cua Driver, purchases stay with the owner |
| Set up Apple access, sign, and upload | [Apple deployment prompt](prompts/deploy-apple.txt) | [Apple runbook](apple-deployment.md), [config template](apple-release.example.json), local preflight below |
| Port iOS to Android or Android to iOS | [Mobile porting prompt](prompts/port-mobile-app.txt) | [Porting structure](mobile-porting.md), including an Isofall worked plan |

The prompts can be copied into another project without this repository. They tell Codex to inspect the actual app and consult current official documentation. Copy the supporting runbook and helper as well when you want the same recorded checks. These artifacts codify the work; they do not establish that a live store deployment or Android port has been completed.

## Apple: setup once, repeat the release

1. **Owner setup:** enroll the correct individual or organization, complete identity/payment/agreements, enable account access, and select an API-key or Xcode authentication route. The owner handles login/MFA and supplies unresolved legal or seller declarations. Reuse these facts and permissions on later runs.
2. **App setup:** Codex resolves the bundle IDs, capabilities, App Store Connect record, signing assets, public policy/support URLs, and listing declarations. Use supported APIs/CLI first, with the required [Cua Driver setup](harness/deploy/CUA-DRIVER.md) for desktop/browser screens where needed.
3. **Each release:** test → archive → App Store export → validate → upload → wait for processing → upload/verify copy and media → submit/release according to the existing user instruction. Retain identifiers and observations so interrupted runs resume at the right step.

Apple controls enrollment verification, processing, and review. The default prompt stops at an uploaded draft. An authorized release can continue after approval; automatic/scheduled release must already be covered by that authorization. See the [official publishing sequence](https://developer.apple.com/help/app-store-connect/manage-your-apps-availability/overview-of-publishing-your-app-on-the-app-store/).

## Local Apple preflight

Requires Python 3.9+; artifact/profile inspection uses macOS and Xcode. Copy [apple-release.example.json](apple-release.example.json) to the app as `apple-release.json`. Set the actual project, scheme, bundle/team, version/build, and artifact paths. Relative artifact/project paths resolve against `--project`; the config path resolves against the current shell directory. For API access, configure environment-variable **names**, then set their values outside the repository. The helper checks key file presence without reading its contents.

From this repository, run:

```sh
python3 tools/apple-preflight.py \
  --project /path/to/app \
  --config /path/to/app/apple-release.json \
  --output /path/to/app/release-output/apple-preflight.json
```

The helper performs read-only local inspection. It does not authenticate, call Apple's API, install signing assets, sign, upload, submit, or release. Only the explicitly supplied `--output` writes a report. Respect an existing `DEVELOPER_DIR`; otherwise the helper uses the standard full-Xcode installation when present without changing global settings.

| Exit | Meaning |
| --- | --- |
| `0` | No failing local checks for the selected goal. Unknown checks still need verification; `store_readiness` remains `unverified`. |
| `1` | Local blockers for that goal are listed in `blocking_local_checks`. Review-only fields do not block a draft binary upload. |
| `2` | Invalid config or inaccessible input/output. Use the template's fields and actual paths. |

This is a preflight, not a complete signature validator or remote deployment client. It checks project/artifact presence, IPA identity/device platform, root provisioning type/team/bundle/expiry, credential references, and review prerequisites. Scheme validity, actual API access, membership, agreements, full signatures/entitlements/extensions, current SDK rules, media contents, and remote state remain explicit follow-up checks. A configuration goal or authorization reference does not grant permission by itself.

### Isofall evidence

[Example config](examples/isofall.apple-release.json) and [recorded preflight](examples/isofall.apple-preflight.json) are from the Lexar app on 2026-10-23. The archive and build 5 IPA exist and match `com.jamesktan.isofall`; the IPA contains a **development profile with a wildcard identifier**, so distribution checks fail. Public support/privacy URLs are also missing for review. Apple access and store state were not queried. The next step is to resolve the signing route and export an App Store IPA, then perform the live checks in the runbook.

Run the helper's regression checks with:

```sh
python3 -m unittest discover -s tools -p 'test_apple_preflight.py' -v
```

## Mobile porting structure

Codex establishes a runnable source baseline, extracts a behavior contract and shared fixtures, implements the target's native core/UI/platform adapters, and verifies both semantic and actual device behavior. It then uses the same `release-output/` workflow for the target. Native defaults are Swift/SwiftUI ↔ Kotlin/Compose; existing Unity or other shared stacks keep their architecture and gain the missing target.

The [detailed structure](mobile-porting.md) defines file ownership for parallel workers, platform mappings, parity evidence, reverse-direction maintenance, and Isofall's renderer/gameplay/audio milestones. It is a draft workflow with an execution prompt; no Android app or automatic source-code converter is included in this change.
