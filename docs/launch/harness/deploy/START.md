# Start ShippyKit in a chat

Run this entry procedure once on the first ShippyKit invocation in the current chat. Do not repeat the menu or update check on every message, nested skill call, worker handoff or resumed tool execution. A new chat can check again. An explicit request to check versions can always run another check.

## Establish the project and recommend a route

Resolve the actual app repository from the user's request/window and read its applicable instructions. Follow [RESUME.md](RESUME.md): run local discovery, then read APP.md, STATE.md and relevant legacy handoffs or section journals. Use the current intent and saved next action to recommend a route; do not infer authorization from files, receipts or successful checks.

```sh
python3 deploy/shippykit.py status --project .
python3 deploy/shippykit.py updates --project .
```

Skip the update command when the user requests offline work or no network. `status` always stays offline; it does not call the update endpoint. A status-only invocation changes no files. If the installed helper is older or missing, inspect the same local evidence directly, note the unavailable capability and continue within scope.

At the first invocation, briefly acknowledge the recommended route and show this compact menu:

- **Resume** — continue the saved next step.
- **Status & setup** — inspect readiness and resolve the prerequisites needed now.
- **Build & install** — build, validate and install on the requested device.
- **Artwork & revisions** — use uploaded media or create in-game assets, icons and marketing compositions; compare revisions and visual directions.
- **Store copy & localization** — refresh factual copy for the requested locales.
- **Versions & changelog** — keep one `MAJOR.MINOR.PATCH` version on every platform, raise build numbers, and record each change with its evidence; `deploy/versions.py status` says each next step ([VERSIONING.md](VERSIONING.md)).
- **Preview & share** — generate the local review site and, if requested, an optional temporary link.
- **Website & domain** — build the public marketing/support/privacy site, host it on Railway and connect a Squarespace domain; `deploy/domains.py status` says each next step ([DOMAINS.md](DOMAINS.md)).
- **Store drafts** — prepare and verify the requested binary, media, copy and store sections in drafts.
- **Update ShippyKit** — refresh the project workflow while preserving app memory and customizations.

For a generic “Run ShippyKit” with no requested action or established next step, show the recommendation and let the user choose. For an explicit task or “Resume ShippyKit,” state the selected route and continue immediately; the menu is a discoverability aid, not a mandatory question or approval gate. Do not change an existing testing/review/release instruction into drafts merely because the menu uses that label. Focused artwork, copy, preview, website, status or install requests keep their scope. Apply the setup/tool checks required by the selected action; no menu choice silently authorizes unrelated software installation, store publication or public sharing.

## Update notifications

The explicit `updates` command first uses Python 3.9+ standard-library HTTPS to read the official VERSION file anonymously:

```text
https://raw.githubusercontent.com/jamesktan/shippykit/main/docs/launch/harness/VERSION
```

It reads `package_version` from this project's `.shippykit/install.json`, checks the fixed endpoint with a five-second transport timeout and a 256-byte response limit, and compares strict semantic versions. Prerelease ordering is respected; build metadata does not change precedence. The anonymous request sends no credentials, follows no redirects and uses no authenticated proxy.

The official repository may be private. Only when the anonymous request returns HTTP 401, 403 or 404, the helper tries the already installed GitHub CLI with its existing GitHub access:

```sh
gh api --hostname github.com --method GET 'repos/jamesktan/shippykit/contents/docs/launch/harness/VERSION?ref=main' --header 'Accept:application/vnd.github.raw+json'
```

This fixed read-only command uses the CLI's existing authentication without extracting or displaying credentials. It disables interactive prompts, debug output and CLI update notices, discards private error output, and caps returned data at 256 bytes. The CLI has a five-second deadline, with bounded cleanup to stop/reap it after timeout or oversized output. There is no fallback for ordinary network errors, and no login, installation or upgrade is attempted when the CLI is absent or cannot access the repository. Neither route sends app/project identifiers or writes a discovery cache. Use `--json` for structured output: `transport` records `anonymous_https` or `existing_github_cli`, and `source_url` identifies the fixed source attempted.

| Result | Meaning and agent response |
| --- | --- |
| `update_available` | Notify once in this chat: “ShippyKit X is available; this project has Y. I can update it when you want.” Continue the selected task. |
| `up_to_date` | No newer version was found at the time of this check. Do not repeatedly announce it. |
| `installed_ahead` | The project version is newer than the official VERSION. Preserve it; do not downgrade. |
| `unavailable` | Receipt missing/invalid, offline/error, or invalid response. Say the check was unavailable when useful and continue; never translate this into “up to date.” |

These results exit successfully because update availability is advisory, not a deployment prerequisite. Invalid command arguments still fail normally. The installed version comes from the installer receipt: unresolved customization conflicts can leave individual files at an older version. Inspect the receipt's conflicts before relying on a new capability, even when its package version is current. No update notice grants authorization to modify the app workflow or download software.

## Perform a requested update

When the user selects **Update ShippyKit** or already authorized that update, use the existing trusted package source. For an existing checkout of the official repository, verify the checkout's origin and preserve its unrelated local edits, then refresh it and run its installer against the actual app:

```sh
git -C /path/to/shippykit pull --ff-only
/path/to/shippykit/setup /path/to/app
```

The official setup command is the repository's `setup`, which invokes its portable installer. If a checkout does not yet exist and obtaining it is authorized:

```sh
git clone --depth 1 https://github.com/jamesktan/shippykit.git ~/shippykit
~/shippykit/setup /path/to/app
```

For an already refreshed flat package at `~/Documents/ShippyKit/`, the equivalent local installation is:

```sh
python3 ~/Documents/ShippyKit/install.py /path/to/app
```

Re-running an old local package does not fetch a newer version; verify its VERSION first. Use the installer's `--dry-run` when a review of proposed changes is useful. Unchanged managed files update normally; customized files remain intact and get incoming candidates for the agent to reconcile. Preserve APP.md, STATE.md, artwork history, existing section journals, app artifacts, unrelated skills and project instructions. Read the final receipt and resolve relevant conflicts before reporting the new workflow ready. Reload skill discovery or open a new chat if the host needs it. Continue the user's original app task after the requested update.
