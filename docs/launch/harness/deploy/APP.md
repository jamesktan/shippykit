# App facts and release intent

The agent populates this from code, build settings, runtime inspection, store reads, and existing user instructions. `unknown` is an unresolved fact, not a request for the owner to fill every field. Automatically select evidence-supported store answers and inform the user; ask only about unresolved facts. Record the source of material facts; do not invent legal/business facts or infer permission to publish.

## Product

| Fact | Value / evidence |
| --- | --- |
| Name, audience, main benefit | unknown |
| Repository and intended GitHub owner | unknown |
| Source revision / local changes included | unknown |
| Existing platform targets and architecture | unknown |
| Strongest real features and capture journeys | unknown |
| Backend, accounts, purchases, ads, analytics and third-party SDKs | unknown |
| Asset ownership/attribution | unknown |
| App icon: existing/placeholder/missing; reuse/generate/replace decision and source | unknown; inspect actual targets using [ICONS.md](ICONS.md) |
| Icon master, platform exports, target wiring and provenance evidence | unknown |
| Listing locales, support URL, privacy-policy URL | unknown |
| Public website: source folder, Railway workspace/project/service IDs, support method, domain, registrar/DNS host, records and forwarding | unknown; follow [DOMAINS.md](DOMAINS.md) |
| Artwork direction, runtime asset locations and generation evidence | unknown |
| User-supplied media index, intended roles and known usage constraints | unknown; follow [MEDIA-INPUTS.md](MEDIA-INPUTS.md) |
| Asset revision journal, stable asset IDs and active visual directions | unknown; follow [ASSET-REVISIONS.md](ASSET-REVISIONS.md) |
| Copy source, verified feature changes, tone and requested locales/fields | unknown |
| Marketing locale audience, terminology/voice and optional localization provider/config | unknown; follow [LOCALIZATION.md](LOCALIZATION.md); distinguish listing languages from implemented app UI languages |

## Build and signing

| Fact | iOS | Android |
| --- | --- | --- |
| Project/workspace/module path | unknown | unknown |
| Scheme / build variant / Unity target | unknown | unknown |
| Bundle ID / applicationId; extensions | unknown | unknown |
| Team ID / Play developer account and app record | unknown | unknown |
| Version and build number / versionCode (MAJOR.MINOR.PATCH; see [VERSIONING.md](VERSIONING.md)) | unknown | unknown |
| Toolchain, SDK, minimum OS | unknown | unknown |
| Meaningful test command | unknown | unknown |
| Build, run and archive/export commands | unknown | unknown |
| Capture device and commands | unknown | unknown |
| Signing mode and verified public certificate identity | unknown | unknown |
| Secret references / account route | unknown | unknown |

Record exact working commands after discovery. API key files and Android keystores live outside source control. Reference environment variables, secure keychain entries, or an existing authenticated account; never paste secret values. Typical references include Apple key path/key ID/issuer env names, Google credential-provider reference, and Android keystore path/alias/password env names. A reference's presence does not establish working access.

## Cua Driver setup

Follow [CUA-DRIVER.md](CUA-DRIVER.md). These are observed facts, not implied approvals.

| Fact | Value / evidence |
| --- | --- |
| Host OS/architecture and usable desktop session | unknown |
| Installed driver version and executable/app path | unknown; reuse a compatible working install |
| Driver daemon and OS permission checks | unknown |
| Task-session window readback and safe evidence path | unknown |
| Approved installer version/source/paths and configuration scope | not granted by this template; record the user's permission reference |

## Requested destination

| Decision | Value / instruction or evidence |
| --- | --- |
| Requested stage: prepare / upload_draft / test / submit_for_review / release | unknown; infer from the user instruction, default deploy/upload to draft |
| Platforms requested and source of the user's choice | unknown; discover targets and offer the missing platform unless already answered |
| Additional platform offered / accepted / declined | unknown; retain the answer on resume |
| Missing target and port scope | unknown; separate missing implementation from missing environment setup |
| Autonomous setup/port permission and instruction reference | not granted by this template; record the user's approved actions, downloads/versions, locations and app-development scope |
| Apple release mode; intended TestFlight group if testing | unknown |
| Google track, tester group and rollout; publishing behavior | unknown |
| Price and countries/regions | unknown |
| Scheduled date/time with timezone, if requested | unknown |
| Existing user authorization covering submission/publication | unknown |
| Local preview output and verification command | `release-output/site/`; follow [PREVIEW.md](PREVIEW.md) |
| Temporary ngrok choice, instruction reference and approved duration | not asked; keep local without explicit opt-in |
| Commit/push instructions and intended remote | follow the actual user instruction |

Keep platform interest separate from permission to install dependencies or develop a port autonomously. Store the proposed plan and readiness evidence in STATE.md before asking for that permission. Reuse existing specific authorization without treating a general deployment instruction as approval for new setup or porting.

## Store decisions and supporting evidence

Follow the [section review](README.md#review-every-store-section) and applicable [Apple](APPLE-SECTIONS.md) / [Google Play](GOOGLE-SECTIONS.md) guide. Record the source of each answer: verified app/backend/SDK behavior, current store evidence, or the user's recorded response. Technical declarations do not require blanket owner confirmation when the evidence resolves them. Ask when the actual fact, intent or legal/business status remains uncertain; then apply the answer and verify the saved selection.

| Decision group | Selected answers / evidence or user-response reference / last verified |
| --- | --- |
| Categories, intended audience and age/content questionnaires | unknown |
| Privacy/data handling, SDKs, ads, account deletion and access | unknown |
| Encryption/export, accessibility and conditional policy questions | unknown |
| Rights, seller/trader status, price/territories and required contacts | unknown |
| Apple / Google section-journal paths and unresolved questions | not assessed |

Keep detailed field choices and readback in the internal section journals. Keep reviewer credentials and sensitive owner information in secure storage and reference them. Mark remaining questions in STATE.md and `release-output/needs-input.md`; remove resolved questions after applying and reading back the answer. Reuse valid recorded answers on resume.
