# Release preview website

Generate this website automatically whenever ShippyKit prepares or refreshes release assets, including a full draft-upload run. It displays the app's icons, screenshots, videos, public store copy and asset revision comparisons in a responsive, self-contained gallery. A phone-only installation does not need new media or a website. This preview is separate from store processing, review and publication.

## Build locally

Use the bundled [preview.py](preview.py) with an existing Python 3.9+ installation. It uses only the standard library; no package install or hosted service is needed. If Python is missing, follow the coordinator's concrete setup-plan permission gate before installing it. Copy this helper along with the rest of `deploy/` when bootstrapping an app.

1. Prepare real media and public listing copy. Follow [ICONS.md](ICONS.md) for existing or generated app icons and [MEDIA-INPUTS.md](MEDIA-INPUTS.md) for user-uploaded photos, video, logos and other marketing inputs. Preserve imported originals under `inputs/`; publish inspected exports from `promo/`, `stores/` or `artwork/review/`. The helper rejects public entries pointing into `inputs/`. Review the actual media and copy for anything that should not be shared; the helper cannot identify private information inside pixels, audio or public prose.
2. Update `release-output/manifest.json`. Its `files` array uses release-root-relative `path`, `kind` and actual `sha256`, plus platform, locale and dimensions/encoding where applicable. Preserve existing entries. Only explicitly selected public kinds are included: `app_store_screenshot`, `app_store_preview`, `preview_poster`, `promo_image`, `promo_video`, `app_icon`, `store_icon`, `launcher_icon`, `asset_revision_preview`, `store_copy` and `preview_copy`. Use the store-media kinds for either platform. Revision previews and their public `asset_history` follow [ASSET-REVISIONS.md](ASSET-REVISIONS.md). Do not relabel raw captures, logs or private notes to get them into the preview.
3. Run from the app repository:

   ```sh
   python3 deploy/preview.py build --release-output release-output
   ```

4. Open `release-output/site/index.html`, or serve the generated site:

   ```sh
   python3 deploy/preview.py serve --site release-output/site --port 8765
   ```

   Use the printed loopback URL. If that port is occupied, select an available one; preserve the existing process. Keep the serving session's handle so it can be stopped precisely.
5. Verify the page at narrow and wide widths, representative images, video playback, public copy and downloads. Check that excluded material is absent. Record the source manifest hash, output path, counts, verification and time in STATE.md. Rebuild after changing any presented assets and restart the owned preview server so it loads the new allowlist; stale website content must not be presented as the latest build.

The builder verifies hashes and rejects unsafe paths and symlinks. It copies only supported public media, escapes text and extracts known public sections from `store_copy` Markdown, omitting review notes and unknown sections. `preview_copy` is an explicit public-only Markdown document: review its entire contents before marking it public. Keep generation prompts/provenance, signing details, reviewer credentials, binaries, logs and deployment reports outside the public site. An empty category stays empty instead of receiving invented assets.

For generated game/app assets, show the selected and actually integrated revision separately, prior alternatives, their visual directions and reasons for changes. Refresh the history after each generation/refinement batch and selection or direction change. The private journal is not a website input: explicitly export its safe review summaries and images to the manifest. Before optional sharing, review historical candidates and event wording as well as the current selection. A comparison is a review surface; changing the app still requires actual integration and validation.

For localized marketing, include each approved locale's copy and media with its exact `locale` field so reviewers can compare wording and overlays. Follow [LOCALIZATION.md](LOCALIZATION.md) for naturalization, field limits and review evidence. Listing locale coverage does not establish translated app UI support.

The generated site has no external scripts, fonts or analytics. Its dedicated server binds to `127.0.0.1` and serves only its generated file allowlist. Do not replace it with a generic server rooted at the repository or `release-output/`. Do not serve that source folder directly through ngrok. An existing unrelated output folder is not a disposable build directory; use a new path if the builder refuses it.

## Offer a temporary ngrok link

After the local preview passes verification, ask once per run unless the user has already answered for this run:

> Would you like a temporary public ngrok link to view this release preview on another device? Anyone with the link can view these selected assets. Keep it local, or share it for 30 minutes?

Recommend **keep local**. Record the answer and requested duration; a decline or no answer leaves it local and does not block deployment. Reuse a still-applicable explicit choice on resume. A past sharing approval is not permission to expose a later release indefinitely. Sharing this preview never authorizes a store release.

### Check and start only after opt-in

1. Inspect `ngrok version`, `ngrok config check` and `ngrok http --help`. Reuse a compatible existing install/account. Check existing sessions and occupied ports without stopping them. Missing ngrok requires a concrete installation plan with the official source, version, host architecture, install path and any configuration changes, then the user's permission before installing. Use the [official download instructions](https://ngrok.com/download). A missing account/authtoken is an owner action: the owner configures it securely using ngrok's onboarding; do not request or put token values in chat, command logs or committed files.
2. Start the allowlisted preview server above if it is not already running, then use the installed CLI's supported equivalent of:

   ```sh
   ngrok http http://127.0.0.1:8765 --inspect=false
   ```

   Use the actual selected port. Keep this invocation in an owned, stoppable session. Do not use `ngrok start --all`, install a background service, reserve a domain, or change another tunnel's configuration. Preserve existing endpoints; if the account's endpoint limit prevents another one, explain the conflict rather than taking one down. See the [official CLI reference](https://ngrok.com/docs/gateway/agent/cli).
3. Obtain this session's actual HTTPS URL and verify both the page and a representative asset through it. A log saying “started” alone is not verification. Account limits, authentication errors and any browser interstitial are reported as observed. Do not return a made-up or stale URL.
4. Record the URL, approved scope/duration, manifest identity, start/stop deadline, process/session handles and exact stop action in STATE.md or a local status report **outside `site/`**. Give the user the working URL and its lifetime. Keep tokens and traffic logs out of public output.

### End the preview cleanly

An ngrok agent endpoint lives while its agent process runs; this does not guarantee a unique one-use hostname. See [endpoint lifetime](https://ngrok.com/docs/gateway/endpoints/agent-endpoints). Establish an actual bounded process lifetime or supervised cleanup before promising automatic expiry. If no reliable timer is available, keep the session supervised and stop it before ending the run; do not silently leave an indefinite background tunnel.

On the approved deadline, cancellation or task completion, stop only the tunnel and preview server started for this run, verify those processes/endpoints have stopped and record the result. If the owner explicitly requests a temporary handoff beyond task completion, retain the agreed deadline, verified cleanup mechanism and exact stop instructions. Never kill every ngrok/Python process. Preserve the local generated site for reopening or rebuilding later.
