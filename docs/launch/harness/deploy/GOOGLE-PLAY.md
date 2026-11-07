# Google Play deployment instructions

Checked **2026-10-23**. Read [README.md](README.md), resolve the app-specific inputs in [APP.md](APP.md), and resume from [STATE.md](STATE.md). These instructions work after copying this `deploy/` folder into another repository; paths below are relative to that repository's root. Use the owner's authorized account and tools. Store build/media/log evidence under `release-output/`; never store credentials in these Markdown files.

For the actual Console review, follow [Review every Google Play section](GOOGLE-SECTIONS.md): discover the displayed sections and conditional forms, apply evidence-supported answers and inform the user, ask about uncertainty, then apply and read back the answer. Keep `release-output/google-sections.md` alongside the separate build/media checkpoints; preserve the requested draft, review or production boundary.

## Establish the intended action

Record package name, developer account, versionCode, track, countries, rollout fraction, release status, and existing authorization. Without an authorized target, prepare a local draft. A draft upload, tester rollout, review submission, and public production rollout are different actions. Reuse explicit authorization already given; resolve only missing facts or scope. Open testing is publicly discoverable; do not silently substitute it for internal/closed testing.

For an authorized upload-only task, use release status `draft`, which does not serve the release to users. Verify the broader edit before committing: a draft release is not a guarantee that unrelated listing changes stay out of review. If committing would submit or publish beyond the user's instruction, save Console drafts where supported and record the remaining transition instead. Test/production rollout needs its specified audience and status. [Track/release API](https://developers.google.com/android-publisher/api-ref/rest/v3/edits.tracks)

## 1. Verify the owner, account, and permissions

- Confirm personal versus organization account, legal identity, developer ID, verified contact details, and current Console requirements. Organizations normally need a D-U-N-S Number. The owner completes enrollment/payment, identity checks, authentication challenges, and legal acceptance; prepare factual entries without inventing claims. Use the required [Cua Driver setup](CUA-DRIVER.md) for these Console GUI steps, verifying installation, permissions and window access first. [Account information](https://support.google.com/googleplay/android-developer/answer/13628312?hl=en)
- For API access, enable Google Play Developer API in the chosen Cloud project; use the owner's service account or supported OAuth user flow. Invite the service-account email in Play Console Users and permissions. Cloud IAM alone does not grant access to the Play app; linking the developer account to a Cloud project is no longer required. Keep credential references in APP.md, actual secrets in the owner's secret store. [API setup](https://developers.google.com/android-publisher/getting_started)
- Grant app-scoped permissions for the work: testing releases, tester-list management, and store presence as needed; production permission only for production work. Testing permission does not authorize production. Do not grant financial/order permissions merely to upload. [Play permissions](https://support.google.com/googleplay/android-developer/answer/9844686?hl=en-GB)

## 2. Bootstrap once; reuse the app thereafter

Find the existing app by package name before creating anything. For an authorized new app, use Play Console Create app and set language/name, app versus game, free/paid, contact, and declarations from verified app evidence and established owner decisions. Apply supported technical choices automatically; ask about unresolved business/legal facts and leave required owner acceptance or identity actions with the owner. Resolve the initial bundle/signing setup through Console. The Edits guide requires an existing app with a prior Console binary upload and does not provide initial app creation or legal consents; its legacy wording says “APK,” while current new-app delivery uses AAB. Do not invent a public-app creation endpoint or change to APK solely because of that wording. [Create app](https://support.google.com/googleplay/android-developer/answer/9859152?hl=en), [Edits limitations](https://developers.google.com/android-publisher/edits)

Confirm Play App Signing enrollment. Sign the AAB with the registered **upload key**; Google signs delivered APKs with the **app signing key**. Neither is the API service-account key. Reuse the registered upload identity, record public certificate fingerprints, and protect keystore/password backups. If the key is missing, use the documented upload-key reset process rather than generating an incompatible replacement. [Signing](https://developer.android.com/studio/publish/app-signing)

## 3. Build and inspect the release bundle

Run the real test and release commands recorded in APP.md, selecting the correct module/flavor (for example, `./gradlew :app:bundleRelease`). Verify the signed AAB's applicationId, versionName/versionCode, target SDK, upload certificate, supported devices, and release configuration. Retain the AAB, mapping/native symbols where applicable, test results, source revision, and SHA-256 under `release-output/builds/android/`. Reconcile existing Play versions before choosing an unused increasing versionCode. A local install or debug APK is not upload evidence. [Bundle upload/update requirements](https://developer.android.com/studio/publish/upload-bundle)

Check the current target-SDK deadline for the app's form factor on every run. As checked, ordinary new apps/updates require Android 16/API 36 from 2026-08-31; Wear/Automotive and TV/XR differ. Record any actually granted extension instead of assuming one. [Current target API requirements](https://support.google.com/googleplay/android-developer/answer/11926878?hl=en)

## 4. Complete the listing and app-content facts

- Prepare localized title/descriptions, category, contact/support details, privacy-policy URL, release notes, pricing, and intended countries. Read current values before updating; preserve unrelated locales and releases.
- Audit app and SDK behavior for Data safety. Complete accurate collection/sharing/security answers even for “no data collected”; apps exclusively on internal testing are exempt from this form. Do not infer privacy answers from the absence of login. [Data safety](https://support.google.com/googleplay/android-developer/answer/10787469?hl=en)
- Complete content rating, ads declaration, target audience, sensitive-permission and other applicable Console questionnaires. Supply working review access, including demo credentials and instructions when functionality is restricted. Apply technical answers supported by verified app/SDK/backend evidence and preserve valid owner decisions; ask only unresolved facts, then apply and read back the answer. Required owner acceptance and identity actions remain with the owner. Use Console where the chosen API cannot complete them. [Review preparation](https://support.google.com/googleplay/android-developer/answer/9859455?hl=en)
- Follow [ICONS.md](ICONS.md) to validate the actual launcher/adaptive icon and the separate Play store icon. Complete icon integration before building the final release bundle.
- Capture actual Android UI. Validate icon, feature graphic, screenshots, device categories, locale, dimensions, and ordering against current requirements; keep a hashed media manifest in `release-output/`. A Play preview video is a **YouTube video URL**, not an MP4 uploaded to Play. Use an existing authorized video or separately authorized YouTube publishing; no channel or playlist substitution. [Preview assets](https://support.google.com/googleplay/android-developer/answer/9866151?hl=en)

## 5. Stage, validate, commit, and observe

Use the app's supported Android publishing client, the bundled [Play helper](#optional-bundled-play-helper), or Play Console. Treat binary and listing work as separate checkpoints. A capture failure need not prevent staging a valid AAB, and missing signing need not prevent authorized listing preparation/uploads. Serialize writes to the same edit/app and retain the publication boundaries above.

1. Serialize changes for this package. Read pending Console changes and current tracks first. Console changes can invalidate API edits; committing an edit can send pending Console changes for review too. Do not edit through Console and API concurrently. [Concurrency rules](https://developers.google.com/android-publisher/concurrency-considerations)
2. Create an edit; persist its ID and expiry in STATE.md. Upload/reuse the exact AAB, upload intended listing images/text, and update only the specified track with its versionCodes, release notes, status, and rollout fraction. Record returned identifiers/hashes after each operation. Existing artifacts must match the intended source and bytes.
3. Call `edits.validate`; retain errors and fix their cause. Validation checks the edit, **not** policy approval or public availability. Re-read the intended change set before commit. [Validate API](https://developers.google.com/android-publisher/api-ref/rest/v3/edits/validate)
4. Commit only within existing authorization for its actual effects. Where supported, use `changesInReviewBehavior=ERROR_IF_IN_REVIEW`; the current default can cancel existing review and submit changes. `changesNotSentForReview` is documented for rejection handling, not a universal no-review/no-publication switch. If the client cannot express safe behavior, use Console to inspect and perform the intended operation. [Commit API](https://developers.google.com/android-publisher/api-ref/rest/v3/edits/commit)
5. Read Publishing overview. Distinguish committed, changes ready to send, in review, rejected, ready to publish, and available. If changes remain ready to send, use the authorized **Send for review** action; do not equate commit success with review submission. Record Google's actual state and pending issues. [Review/publishing controls](https://support.google.com/googleplay/android-developer/answer/9859654?hl=en)

For `upload_draft`, read back the accepted AAB/versionCode in the exact intended track with draft status. Reopen that release and the affected store-listing locales; verify screenshot/graphic counts, order, content and saved public text against the manifest and copy. Record each result separately. An uploaded bundle alone is incomplete when requested listing assets or copy are missing; an uncommitted edit that may expire is not a durable completed draft. If the safe save/commit transition is blocked, preserve its edit/Console evidence and next action without promoting the release or claiming completion.

### Optional bundled Play helper

Use `play-upload.mjs` with an existing Node.js 18+ runtime; it uses built-in modules. Read `node deploy/play-upload.mjs --help` and use the actual app facts from APP.md. The helper authenticates with the owner's **service-account JSON key** through `PLAY_SERVICE_ACCOUNT_KEY` or `GOOGLE_APPLICATION_CREDENTIALS`. Invite that service account in Play Console with app-scoped permissions for the requested parts: testing releases for `bundle`, store presence for `listing` and `images` (step 1). Keep the key outside committed files and logs. The app must already exist with its first bundle uploaded through Console (step 2). Do not create a Cloud project, key or invitation merely to use this optional helper; Console remains the route when API access is unavailable. API behavior checked **2026-10-28**.

Inputs come from `release-output/manifest.json`:

- `android_bundle`: `path`, `sha256`, `version_code` and `package_name` for the signed AAB under `builds/android/`, or `--aab PATH --aab-sha256 HASH` with `--version-code`. The helper checks the hash, bundle structure and JAR signature. Play reports the versionCode it read; a mismatch stops the run before commit.
- `store_copy` entries for `stores/android/<locale>/listing.md`. `Title`, `Short description` and `Description` update that locale's listing; `Release notes` go on the release. All are counted against Play limits. The preview video URL and other listing fields are untouched.
- Entries with `play_image_type`: `phoneScreenshots`, `sevenInchScreenshots`, `tenInchScreenshots`, `tvScreenshots`, `wearScreenshots`, `featureGraphic`, `icon` or `tvBanner`. They upload per locale in manifest `order` after format, size and count checks.

Start with a local-only plan, then rehearse, replacing placeholders from APP.md:

```sh
node deploy/play-upload.mjs plan --release-output release-output --package PACKAGE
node deploy/play-upload.mjs upload --release-output release-output --package PACKAGE \
  --parts bundle,listing,images
```

`upload` stages only the named `--parts`, all in one edit. It checks conflicts before the first write, validates, and rereads the staged edit. Without `--commit` it deletes the edit: a rehearsal, not a durable draft. Add `--commit` only when existing authorization covers the commit's actual effects (step 4). The helper always commits with `changesInReviewBehavior=ERROR_IF_IN_REVIEW`, then reads the result back in a fresh edit. Changes already in review return `pending_external` (exit 2) with nothing committed. When Play already matches the manifest, nothing is committed.

The default is a `draft` release on `internal`. `--track` selects another testing track; production tracks are refused. `--status completed` serves the build to that track's testers once committed. `--replace` is required to replace listing images that are not in the manifest, or another draft release on the track. Releases with other statuses are kept, and a build already served on the track is never turned back into a draft.

`status` compares the bundle, track release, listing text and images with the manifest in a read-only edit. The receipt defaults to `release-output/play-upload-receipt.json`; copy edit IDs and outcomes into STATE.md. A commit with an unknown outcome is `pending_external`: run `status` and reconcile before retrying. `verified` covers only the requested parts. Play's returned SHA-256 confirms the remote bundle bytes; each image upload must also return the local file's SHA-256, or the run stops before commit. A commit is not review approval or availability, so continue with step 5. The helper does not complete app content forms, Data safety, pricing, or **Send for review**.

## 6. Respect testing gates and the publishing mode

Personal accounts created after **2023-11-13** must run a closed test with at least **12 testers continuously opted in for 14 days**, then apply for production access and answer readiness questions. This is a real external gate; record eligibility and evidence, never simulate testers or claim production access from an internal test. [Personal-account testing](https://support.google.com/googleplay/android-developer/answer/14151465?hl=en)

Verify managed publishing before relying on an approval hold. It cannot be used for an app's first publication; Google recommends publishing to a closed-testing track first when planning a managed launch. When applicable and enabled, approved held changes still need **Publish changes**. Standard publishing can make approved changes available automatically, so submitting those changes needs authorization for that release. Managed publishing also has exceptions; inspect the actual affected changes. [Publishing behavior](https://support.google.com/googleplay/android-developer/answer/9859654?hl=en)

Apply only the authorized track/country/fraction. Confirm the intended version is available to the relevant testers or production audience, not merely present as an uploaded bundle. Google review remains external; report pending review as pending, with the next check, rather than promising a launch date.

## 7. Resume from evidence

Update STATE.md with package/developer ID, source and AAB hash, versionCode, edit ID/expiry, exact track/release state, listing/media hashes, commit response, review/publishing observations, testing-gate status, authorization reference, and next action. Keep redacted logs and artifacts under `release-output/`; never include tokens, service-account JSON, keystores, passwords, or reviewer credentials.

On timeout, query remote state before retrying writes. On expired/invalidated edits, reconcile the current app and create a fresh edit without overwriting other work. For 429/transient server errors, honor retry hints and use bounded backoff; fix permissions/validation/rejection causes before retrying. Persist pending external work when this run's budget ends. Report the exact achieved checkpoint—built, uploaded draft, distributed to testers, sent for review, approved/held, or publicly available—and the evidence proving it.
