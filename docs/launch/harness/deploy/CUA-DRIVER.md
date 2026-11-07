# Cua Driver requirement and setup

Cua Driver is ShippyKit's required driver for automated desktop and browser setup, including Xcode and store-account screens. Check it during onboarding. Installation, OS permissions and a successful window readback must be verified before dependent GUI work. Prefer supported APIs/CLIs for build and upload operations; a missing driver must not block independent builds, captures or phone installs that already work through those tools.

This requirement is not installation permission. Reuse an existing working installation. If missing or incompatible, present the exact version, official download, paths, configuration changes and owner actions; obtain permission before installing or upgrading. The owner has already selected Cua Driver, so ask about the concrete setup plan, not which driver to use. Do not silently substitute another driver or bypass missing permissions.

## Requirements

- A logged-in, unlocked desktop session on the machine being controlled. A headless build host alone is insufficient for GUI work.
- macOS 14+, Windows 10/11, or a supported Linux desktop. The documented Linux quickstart uses x86_64, X11/XWayland and AT-SPI 2; verify other architectures/compositors against current support before proposing installation. iOS building still requires a compatible Mac/Xcode route. [Quickstart](https://cua.ai/docs/cua-driver/quickstart), [platform support](https://cua.ai/docs/cua-driver/concepts/platform-support).
- Network access to the official installer and GitHub release assets; permission to write the proposed install locations. On macOS, the owner must enable Accessibility and Screen Recording for the installed CuaDriver app.
- An agent that can invoke the CLI or an already configured Cua Driver MCP server. The CLI is enough for this harness; adding MCP registrations or agent skills is a separate configuration change, not an automatic prerequisite.
- Authorized Apple/Google access for the requested store work. Driver installation does not establish enrollment, account access, device trust or signing readiness. Passwords, MFA, agreements and OS permission prompts remain with the owner.

## 1. Inspect and propose

On macOS/Linux, locate the driver without installing anything:

```sh
command -v cua-driver
# If not on PATH, check the standard location:
test -x "$HOME/.local/bin/cua-driver"
```

On Windows, use `Get-Command cua-driver -ErrorAction SilentlyContinue` and check `%LOCALAPPDATA%\Programs\Cua\cua-driver\bin\cua-driver.exe`. For an existing executable, inspect `--version`, `doctor`, `status`, and on macOS `permissions status`. Read the diagnostic results, not just the exit code. Record failures and affected steps in STATE.md and `release-output/needs-input.md`.

For a new installation, resolve a compatible stable release from the [official releases](https://github.com/trycua/cua/releases), then pin the version in the permission request and command. **0.37.0** is the example reviewed on 2026-10-24; it is not a promise of the latest version on future runs. Recheck installer behavior and paths before execution. [Release reviewed](https://github.com/trycua/cua/releases/tag/cua-driver-rs-v0.37.0).

State the proposed app/binary and state locations, whether an existing installation will be replaced, and any PATH, startup-service or agent configuration changes. Obtain approval for those specific changes. Do not install missing prerequisites or elevate privileges beyond that approval.

Installers can stop existing driver processes even when startup registration is disabled. Include any daemon interruption/restart in the plan, inspect active sessions and defer an upgrade while unrelated sessions are using that installation.

## 2. Install after approval

### macOS and Linux

Download and inspect the official script before executing the approved plan. The wrapper also downloads its official helper. These commands pin the reviewed example and avoid editing shell startup files:

```sh
shippykit_cua_installer="$(mktemp "${TMPDIR:-/tmp}/shippykit-cua-install.XXXXXX")"
curl -fsSL https://cua.ai/driver/install.sh -o "$shippykit_cua_installer"
# Inspect this script and its referenced helper; execute only after approval.
CUA_DRIVER_RS_VERSION=0.37.0 /bin/bash "$shippykit_cua_installer" --no-modify-path
"$HOME/.local/bin/cua-driver" --version
```

On macOS, the reviewed installer places `CuaDriver.app` in `/Applications/`, exposes `~/.local/bin/cua-driver`, and uses `~/.cua-driver/` for local state. On Linux, its user-local binary link points into packages under `~/.cua-driver/`. Respect existing custom locations. Use the absolute executable path if the command is not on PATH. Do not use `sudo` or alter shell startup files as an unapproved fallback. [Official installer](https://cua.ai/driver/install.sh), [installer helper](https://cua.ai/driver/_install-rust.sh).

### Windows

Download and review the [official PowerShell installer](https://cua.ai/driver/install.ps1). In the approved desktop session:

```powershell
$shippykitCuaInstaller = Join-Path $env:TEMP 'shippykit-cua-install.ps1'
Invoke-WebRequest https://cua.ai/driver/install.ps1 -OutFile $shippykitCuaInstaller
# Review first. An existing CUA_DRIVER_RS_VERSION overrides -Release; reconcile it with the approved version.
& $shippykitCuaInstaller -Release 0.37.0 -NoPathUpdate -NoAutoStart
$shippykitCuaDriver = Join-Path $env:LOCALAPPDATA 'Programs\Cua\cua-driver\bin\cua-driver.exe'
& $shippykitCuaDriver --version
```

The reviewed layout uses `%LOCALAPPDATA%\Programs\Cua\cua-driver\bin` and `%USERPROFILE%\.cua-driver`. The default installer can register a login task; the example opts out. An upgrade may refresh an existing task, so include that in the plan. Start a task-owned daemon with `serve` in a separate terminal, or, if login-service setup was approved, use `autostart enable`, `autostart kick`, then `autostart status`. Let the owner handle any UAC prompt. Do not bypass an execution policy; report the required owner/administrator action instead.

## 3. Grant permissions and start the service

On macOS, have the owner run the installed executable's `permissions grant`, enable **CuaDriver** in System Settings → Privacy & Security → Accessibility and Screen Recording (or Screen & System Audio Recording), and accept any requested relaunch. Run `permissions status` again to verify both grants. Opening Settings does not itself grant access. For the default install path:

```sh
"$HOME/.local/bin/cua-driver" permissions grant
# Owner enables both permissions and completes any requested relaunch.
"$HOME/.local/bin/cua-driver" permissions status
```

See the [official macOS setup](https://cua.ai/docs/cua-driver/quickstart).

On Windows/Linux, follow `doctor` for the active desktop/display session and inspect the installed `serve --help` before starting a missing daemon. Linux accessibility, display or compositor dependencies must be named in the setup plan before installation. A missing desktop is an owner/environment blocker, not a reason to substitute fabricated screenshots.

Preserve a running daemon's permission mode. Do not restart it with broader access or use approval-bypass flags. Attaching to an existing signed-in browser profile may require a separate driver grant; follow that boundary and keep account login with the owner. [Driver permissions](https://cua.ai/docs/cua-driver/guides/permissions).

## 4. Verify actual access

Use the resolved executable path for these commands if it is not on PATH:

```sh
cua-driver --version
cua-driver doctor
cua-driver status
cua-driver list-tools
cua-driver describe start_session
cua-driver describe get_window_state
cua-driver describe end_session
```

Create a unique task session using the installed schema. Discover the intended app/window, then read a fresh window snapshot with that session. Confirm the expected app is accessible; executable presence and a running daemon alone are insufficient. End only this verification session. Leave unrelated windows and a shared daemon intact. [CLI reference](https://cua.ai/docs/cua-driver/reference/cli/serve-and-configure).

Record the observed version/path, OS/session, daemon and permission results, window-readback evidence, setup permission and remaining blockers in APP.md/STATE.md. Keep screenshots/logs local and redact unrelated private content. Never commit credentials, browser profiles or session tokens.

## 5. Use during deployment

Several agents can share one daemon and one signed-in browser. Run `cua-driver sessions` before driving. While another session is active, wait until it has been idle for a few minutes, or coordinate through the owner. Never type into a window another session is using. Give the task its own session label, open a dedicated window (in Chrome, `invoke_menu` with `File` › `New Window`), and act only on that window ID. An ended label must be revived with `start_session` or replaced with a new one.

For each GUI step: identify the intended result, take a fresh snapshot, perform one scoped action, and verify the resulting state. Discover tool schemas rather than guessing arguments; prefer accessibility elements over coordinates. Browser preparation follows the installed driver's grant rules. Installation permission does not authorize account changes, store submission or public release beyond the user's existing scope. Save actual outcomes, and end only the session created for this task.
