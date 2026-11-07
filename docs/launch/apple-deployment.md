# Apple deployment: owner setup through App Store release

Checked against official Apple documentation on **2026-10-23**. This is a reusable operating procedure; writing it performs no enrollment, account changes, uploads, submissions, or releases. Recheck Apple's linked requirements before each launch.

Use [the release config](apple-release.example.json), [the Codex deployment prompt](prompts/deploy-apple.txt), and [the local preflight helper](../../tools/apple-preflight.py). The helper inspects local evidence; it does not authenticate with Apple, prove remote readiness, provision signing assets, or upload. Existing provider adapters and synthetic tests are not evidence of a successful live deployment.

## Define the intended outcome

Record the app, version, build, and the user's existing authorization before acting. `release.goal` is one of `upload_draft`, `testflight_internal`, `submit_for_review`, or `release`. `release.mode` is `manual`, `automatic`, or `scheduled`; scheduled release also needs `not_before` with an explicit timezone. `authorization_ref` points to the instruction authorizing the relevant actions. Reuse authorization already given; resolve only missing scope or facts. Automatic/scheduled release can make the app public after approval without another click, so selecting either for a review submission requires authorization for that public release too.

Keep these outcomes distinct:

| Checkpoint | Evidence required |
| --- | --- |
| Tested locally | Test results tied to a source revision and toolchain |
| Distribution export ready | App Store Connect export completed; IPA identity, signing evidence, and SHA-256 recorded |
| Uploaded | Apple's upload ID or delivery receipt for that build |
| Processed | Apple's successful processing state and build ID |
| Submitted for review | Submission ID and observed submitted state |
| Approved, awaiting release | Apple's approval/release state; the version is not necessarily public |
| Released | Release state and the correct version visible in the intended storefronts |

Uploading is not publishing. Apple processes builds and conducts App Review outside the agent's control. TestFlight distribution is also a separate outcome from an App Store release. [Apple publishing workflow](https://developer.apple.com/help/app-store-connect/manage-your-apps-availability/overview-of-publishing-your-app-on-the-app-store/)

## One-time owner onboarding

1. **Choose the actual seller.** Use an individual enrollment for the individual/sole proprietor, or an organization enrollment for an eligible legal entity. An individual seller uses their legal name. Organizations need an authorized person, a legal entity, and normally a D-U-N-S Number. The Apple Account needs two-factor authentication. Gather these facts before opening enrollment. [Enrollment requirements](https://developer.apple.com/programs/enroll/)
2. **Enroll in the Apple Developer Program.** The owner completes identity verification, accepts the agreement, and pays the displayed membership charge. Apple lists the standard annual membership at US$99; use the checkout's applicable local price. Wait for active enrollment and record the verified Team ID. A free development account is insufficient for App Store distribution. [Program membership](https://developer.apple.com/programs/)
3. **Open App Store Connect and settle applicable agreements.** The Account Holder accepts legal agreements. Paid apps or In-App Purchases additionally need the Paid Apps Agreement and applicable tax/banking setup. Do not infer that all free apps need paid-sales onboarding. Record agreement status, not private banking or tax values. [Agreements](https://developer.apple.com/help/app-store-connect/manage-agreements/sign-and-update-agreements/), [tax information](https://developer.apple.com/help/app-store-connect/manage-tax-information/provide-tax-information), [banking](https://developer.apple.com/help/app-store-connect/manage-banking-information/enter-banking-information/)
4. **Delegate only the needed access.** Invite the operator through Users and Access, restrict app access where available, and choose the authentication route below. For an individually enrolled owner, invited App Store Connect users do not thereby become Developer Program team members with signing access. [Roles and access](https://developer.apple.com/help/account/access/roles)
5. **Prepare applicable seller declarations.** The owner supplies truthful rights, contact, and regional declarations. For EU distribution, establish trader status and any required contact verification; do not infer status from whether the app is free. [EU trader requirements](https://developer.apple.com/help/app-store-connect/manage-compliance-information/manage-european-union-digital-services-act-trader-requirements/)

Prefer official API/CLI operations for repeat work. Use Browser Use for enrollment, Users and Access, initial app setup, and settings absent from the chosen API client; use CUA for Xcode Accounts or a native authentication dialog. Navigate and prepare factual entries within the authorized task. The owner handles their password, 2FA, identity/payment steps, agreement acceptance, and unresolved legal claims. Do not request these secrets in chat or invent answers. A blocked owner step need not block independent testing, metadata drafting, or media validation.

## Keep authentication and signing separate

| Asset or access | What it enables | What it does not prove |
| --- | --- | --- |
| App Store Connect API key (`.p8`) | Signed API authentication with that key's permissions | Possession of a code-signing private key or usable profile |
| Apple Distribution certificate plus its private key | Local distribution signing, when matched to the app/profile | App Store Connect authorization or approved metadata |
| App Store provisioning profile | Matching team, App ID, entitlements, and distribution certificate | A successful upload or approval |
| Xcode account session | Xcode's authorized account/provisioning operations | That cached signing assets or remote membership remain valid |

An Apple Development certificate/profile supports development. A distribution certificate alone is insufficient: local signing needs its private key, and the correct profile must cover the app and entitlements. Automatic signing can manage distribution profiles; manual App Store profile creation requires Account Holder or Admin. Reuse matching valid assets instead of issuing certificates on every run. [Certificates](https://developer.apple.com/help/account/certificates/certificates-overview), [App Store profiles](https://developer.apple.com/help/account/provisioning-profiles/create-an-app-store-provisioning-profile)

For API access, the Account Holder requests access in Users and Access → Integrations → App Store Connect API. An Account Holder or Admin can create team keys. Download the private key once into an appropriate secret store; retain only its reference in config. [API setup](https://developer.apple.com/help/app-store-connect/get-started/app-store-connect-api/)

Choose the narrowest viable route:

| Route | Scope and use |
| --- | --- |
| Individual API key | Inherits the user's role and app access. Suitable for supported operations on assigned apps. **Cannot access provisioning endpoints**, Sales/Finance, or `notaryTool`. It is not a substitute for a team provisioning key. |
| Team API key | Role-scoped, but applies across **all apps** in the account. Keep provisioning/bootstrap access separate from routine release access where practical. |
| Xcode account | Owner signs in through Xcode when this is the selected provisioning route; do not export session credentials into the repo. |

Apple documents these key restrictions explicitly. Team and individual JWT claims differ; the implementation must support the selected type rather than synthesizing an issuer ID. [API key types](https://developer.apple.com/documentation/AppStoreConnectAPI/creating-api-keys-for-app-store-connect-api)

Developer is sufficient for build upload. App Manager is sufficient for app-record creation and review/release operations; routine automation does not need Account Holder merely to submit a version. Additional portal/signing permissions must be evaluated separately. [Upload roles](https://developer.apple.com/help/app-store-connect/manage-builds/upload-builds), [app-record roles](https://developer.apple.com/help/app-store-connect/create-an-app-record/add-a-new-app), [submission roles](https://developer.apple.com/help/app-store-connect/manage-submissions-to-app-review/submit-an-app/)

## Preflight each app

The config uses `schema_version: 1` and intentionally stays small:

| Config group | Inputs |
| --- | --- |
| `app` | `project`, `scheme`, `bundle_id`, `team_id`, `version`, `build_number` |
| `access` | `mode`: `xcode_account`, `team_api_key`, or `individual_api_key`; environment-variable names in `key_path_env`, `key_id_env`, `issuer_id_env` where applicable |
| `signing` | `style`: `automatic` or `manual` |
| `release` | `goal`, `mode`, `not_before`, `authorization_ref` |
| `listing` | `privacy_policy_url`, `support_url` |
| `artifacts` | `archive`, `ipa`, `media_manifest` |

Separately retain verified checkpoint evidence: enrollment/agreement state, effective role/app scope, App Store Connect app ID, SKU, primary locale, capability inventory, signing/profile expiry, build/upload/submission IDs, source commit, artifact hashes, metadata/media revision, declarations, pricing/territories, review contact, and release authorization. Mark unqueried remote facts **unknown**. File existence, environment-variable presence, or a development-signed archive cannot establish remote readiness.

Read-only checks may inspect Xcode version, build settings, `security find-identity -v -p codesigning`, archive metadata, profile metadata, and signatures. Keep private keys and full profiles/device lists out of logs. Respect the caller's `DEVELOPER_DIR`; do not change global `xcode-select`. Before building, check Apple's current SDK/upload requirements instead of freezing this document to a historical Xcode cutoff. [Upload requirements](https://developer.apple.com/help/app-store-connect/manage-builds/upload-builds)

## Repeatable per-app flow

### 1. Resolve identifiers and the app record

Query the team's bundle IDs and reuse the exact identifier. Register an explicit App ID only if absent, then enable only the capabilities the project actually uses. Include extension targets and their identifiers. Regenerate affected profiles after capability changes; do not silently reuse a profile with outdated entitlements. [Bundle ID API](https://developer.apple.com/documentation/appstoreconnectapi/bundle-ids), [profile updates](https://developer.apple.com/help/account/provisioning-profiles/edit-download-or-delete-profiles)

Find the App Store Connect record by bundle ID, for example `GET /v1/apps?filter[bundleId]=…`; persist its Apple ID. If absent, use Apps → New App through Browser Use/CUA unless the selected official API supports that creation operation. Supply platform, name, primary language, bundle ID, SKU, and app access. Reuse the existing record on later runs. Do not invent a `POST /apps` endpoint. The bundle ID becomes immutable for that record after a build upload. [App creation](https://developer.apple.com/help/app-store-connect/create-an-app-record/add-a-new-app), [querying an app](https://developer.apple.com/documentation/appstoreconnectapi/uploading-app-previews), [bundle ID changes](https://developer.apple.com/documentation/xcode/changing-the-bundle-identifier)

### 2. Test, archive, and export for App Store Connect

Run the project's meaningful tests and real-device/simulator checks. Resolve the version/build number before archiving and record the source revision. Use a generic iOS device destination, not a simulator archive. Retain the archive and symbols for the distributed build. [Distribution preparation](https://developer.apple.com/documentation/xcode/preparing-your-app-for-distribution), [debug information](https://developer.apple.com/documentation/xcode/building-your-app-to-include-debugging-information)

Example commands after resolving these variables from the app's config:

```sh
xcrun xcodebuild -project "$APPLE_PROJECT" -scheme "$APPLE_SCHEME" \
  -configuration Release -destination 'generic/platform=iOS' \
  -archivePath "$APPLE_ARCHIVE" archive

xcrun xcodebuild -exportArchive -archivePath "$APPLE_ARCHIVE" \
  -exportPath "$APPLE_EXPORT_DIR" -exportOptionsPlist "$APPLE_EXPORT_OPTIONS"
```

Use `-workspace` instead of `-project` for a workspace-based app. The selected project/settings must resolve the expected team and version. Export options must explicitly set `method = app-store-connect`, `destination = export`, the verified `teamID`, and the chosen `signingStyle`. Manual signing also needs the correct certificate/profile mapping for every signed target. A `debugging` or `release-testing` IPA is not an App Store export. Check the installed `xcrun xcodebuild -help` for supported options. [Xcode distribution methods](https://developer.apple.com/documentation/xcode/distributing-your-app-for-beta-testing-and-releases)

`-allowProvisioningUpdates` is a remote mutation permission, not a diagnostic flag: Xcode may create/update identifiers, certificates, and profiles. Add it only within authorized provisioning work. Installed Xcode help specifies either an Xcode account or the combined `-authenticationKeyPath`, `-authenticationKeyID`, and `-authenticationKeyIssuerID` arguments. This provisioning path requires a suitable team key; an individual key cannot supply provisioning access. No saved Xcode account is therefore not an absolute blocker if another supported route is valid. App Store archiving does not require registering a simulator or passing `-allowProvisioningDeviceRegistration`.

Verify export success, actual IPA bundle ID/version/build/team, embedded entitlements/profile, archive-to-export consistency, ZIP integrity, and code signatures. Record hashes after export. An archive may be re-signed during export, so inspect the exported app rather than guessing its distribution method from the archive alone. Keep signed artifacts and profiles in controlled artifact storage, not source control.

### 3. Prepare the listing and factual declarations

Prepare these while the build runs; compare desired content with current Apple state before writing:

| Area | Required preparation |
| --- | --- |
| Listing | App name, category, localized description/keywords, copyright, support URL, and version-specific fields such as What's New for updates. Check the current required/editable-field matrix. [Property requirements](https://developer.apple.com/help/app-store-connect/reference/app-information/required-localizable-and-editable-properties/) |
| Media | Genuine app screenshots per supported display family and locale; previews if desired. Validate dimensions, format, order, and current slot requirements. Do not assume one prior app's iPhone sizes cover iPad or every future release. [Screenshot specifications](https://developer.apple.com/help/app-store-connect/reference/app-information/screenshot-specifications), [media upload](https://developer.apple.com/help/app-store-connect/manage-app-information/upload-app-previews-and-screenshots/) |
| Privacy | Reachable privacy-policy URL and accurate App Privacy answers covering the app and third-party SDKs. Determine actual data handling rather than inferring “no data” from lack of login. [App Privacy](https://developer.apple.com/help/app-store-connect/manage-app-information/manage-app-privacy) |
| Export | Audit encryption use, including libraries and OS crypto; obtain the owner's supported answers and any required documentation. Do not automatically set an exemption in `Info.plist` merely to bypass questions. [Export compliance](https://developer.apple.com/help/app-store-connect/manage-app-information/overview-of-export-compliance/) |
| Age/content | Answer the current questionnaire from actual content and capabilities; preserve Apple's resulting global/regional ratings. Do not hard-code a rating from the genre. [Age ratings](https://developer.apple.com/help/app-store-connect/manage-app-information/set-an-app-age-rating/) |
| Commercial availability | Explicit price, including free; intended countries/regions; applicable agreements and regional declarations. Do not silently select every territory. [Pricing](https://developer.apple.com/help/app-store-connect/manage-app-pricing/set-a-price/), [availability](https://developer.apple.com/help/app-store-connect/manage-your-apps-availability/manage-availability-for-your-app-on-the-app-store) |
| Review access | Working contact details, review notes, and demo credentials/instructions when access requires them. Make the submitted functionality reachable by the reviewer. [App submission](https://developer.apple.com/help/app-store-connect/manage-submissions-to-app-review/submit-an-app/) |

Use the official API for supported listing operations. Asset uploads follow reservation, instructed byte transfer, commit, and processing verification. Store asset IDs and hashes to avoid duplicate uploads; replace or reorder only the intended assets. Browser Use is a fallback for unsupported questionnaires/settings. [Asset upload protocol](https://developer.apple.com/documentation/appstoreconnectapi/uploading-assets-to-app-store-connect)

### 4. Upload and wait for the exact build

Prefer the implemented official API/CLI route. Apple's native build-delivery API creates a BuildUpload, creates its BuildUploadFile, returns transfer instructions, and processes the completed upload. Use that protocol only when the client implements it. Official Transporter with JWT authentication or Xcode distribution remains a valid alternative. Do not treat existing adapter test coverage as proof that a live upload works. [Native build-delivery API](https://developer.apple.com/videos/play/wwdc2025/324/), [supported upload tools](https://developer.apple.com/help/app-store-connect/manage-builds/upload-builds)

Save the delivery receipt/upload ID immediately, then poll the app/platform/version/build tuple and retain the resulting build ID. `Processing` is pending, `Failed` requires reading and correcting Apple's errors, and `Complete` indicates successful upload processing. Inspect warnings too. Apple advises escalation if processing lasts more than 24 hours. A failed upload can reuse its build number; do not assume every failed transfer requires a new number. Conversely, do not overwrite/reupload an already processed build blindly. [Build upload statuses](https://developer.apple.com/help/app-store-connect/reference/app-uploads/build-upload-statuses)

For `upload_draft`, stop after the requested upload/processing evidence. For `testflight_internal`, complete the authorized internal testing setup and report its actual availability; this goal does not authorize public App Store release.

### 5. Submit the selected version for review

Read back the precise build association, listing, media, declarations, price/territories, and release option. Tie them to the artifact/metadata revision covered by the user's instruction. Execute submission when already authorized; if authorization or a necessary fact is missing, present the concrete prepared version and the specific missing decision.

“Add for Review” prepares a submission; “Submit for Review” sends it. With the API, create/reuse the review submission, associate the intended items, and perform the submit transition. Save its ID and verify the returned state before reporting submission. Poll or consume verified notifications; do not promise Apple's approval or a completion time. [Submission procedure](https://developer.apple.com/help/app-store-connect/manage-submissions-to-app-review/submit-an-app/), [review-submission API](https://developer.apple.com/documentation/appstoreconnectapi/review-submissions)

On rejection, preserve Apple's messages, identify the actual affected binary/metadata, and fix the cause before resubmitting. New binary contents require a corresponding build and renewed validation. Do not retry the same rejection as a transient transport failure. [Unresolved review issues](https://developer.apple.com/help/app-store-connect/manage-submissions-to-app-review/manage-a-submission-with-unresolved-issues/)

### 6. Apply the authorized release mode and verify

- **Manual:** after approval, wait for Pending Developer Release; release only when the recorded authorization includes public release. An existing instruction to release when approved is sufficient—do not ask again solely because approval arrived.
- **Automatic:** release follows approval; establish this choice before submitting.
- **Scheduled:** Apple releases after approval and no earlier than the selected date. The date cannot guarantee approval or exact public availability.

Read back the selected option. Apple notes that visibility can take up to 24 hours after release; verify the correct version in the intended storefronts before reporting it as publicly available. Phased release is an optional mechanism for version updates, not an initial-launch substitute or a private beta. [Release options](https://developer.apple.com/help/app-store-connect/manage-your-apps-availability/select-an-app-store-version-release-option/), [phased updates](https://developer.apple.com/help/app-store-connect/update-your-app/release-a-version-update-in-phases)

## Resume, retry, and report honestly

Keep a small durable journal alongside the release evidence, with one record per intended operation: app/platform/version/build, input hash, Apple resource ID, observed state/time, redacted response/error, and next action. Write the intended action before a network mutation and reconcile Apple's state after uncertain outcomes. This is a workflow recommendation, not a claim that Apple supports arbitrary idempotency headers.

| Failure or interruption | Recovery |
| --- | --- |
| Authentication/401 | Check key type, JWT claims/expiry, local clock, and key revocation. Refresh supported short-lived authentication; never print the key/token. |
| Permission/403 | Check effective role/app access, provisioning restrictions, membership, and agreement status. Report the missing permission; do not automatically broaden access. |
| Conflict/409 or lost create response | Read the existing resource and compare identity/state before deciding whether anything remains to create. |
| Validation/400/422 | Preserve Apple's field pointer/code, correct the factual input or artifact, then retry that operation. |
| Rate limit/429 or transient network/5xx | Honor `Retry-After` when present; otherwise use bounded exponential backoff with jitter. Reconcile potentially completed writes before retrying. |
| Processing/review exceeds this run's budget | Persist the remote IDs and last state; report `pending_external` and resume polling later. A local timeout does not establish remote failure or success. |
| Expired/mismatched signing assets | Reuse another valid matching asset or perform authorized renewal/provisioning; rebuild/export and revalidate as necessary. |

Poll with increasing intervals and a finite run budget; stop on terminal failure. Never repeatedly submit, release, revoke certificates, or regenerate app records to make an unknown state disappear. Protect `.p8`/`.p12` files, private keys, account sessions, demo credentials, JWTs, signed upload URLs, and profile contents. Evidence should include hashes and identifiers, not secrets.

End each run with the achieved checkpoint, actual app/version/build and Apple IDs, test/archive/export/upload evidence, release mode, outstanding owner action or Apple state, and the exact next resumable step. Use `blocked_owner`, `pending_external`, or `failed` where appropriate; reserve “released” for verified release evidence.

## Isofall: why the checkpoints matter

The local case at `/Volumes/Lexar/Projects/Isofall` was inspected on 2026-10-23. Its recorded build 5 evidence showed a valid development archive and `debugging` IPA for `com.jamesktan.isofall`, team `CUYMUDSGA4`. A distribution identity existed, but no matching App Store distribution profile was available. The attempted App Store export reported **No Accounts** and **No profiles**. These are observations from that run, not a permanent statement about the account.

Resume by verifying active membership/team access and selecting the owner Xcode-account route or a supported team-key provisioning route; resolve/reuse the explicit App ID and app record, then create/download the matching distribution profile and export again. The successful development export and phone installation do not establish App Store readiness. Re-read Isofall's `docs/signing-status.md` and retained export logs before acting; no enrollment, upload, review submission, or public release is established by this document.
