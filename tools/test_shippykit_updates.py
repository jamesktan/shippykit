"""No real network requests: exercise update notifications with bounded fakes."""
import contextlib
import http.client
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
import urllib.error
from unittest import mock

sys.dont_write_bytecode = True
HELPER = Path(__file__).resolve().parents[1] / "docs/launch/harness/deploy/shippykit.py"
SPEC = importlib.util.spec_from_file_location("shippykit_updates", HELPER)
updates = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(updates)


class Response:
    def __init__(self, body=b"0.2.0\n", code=200, url=None):
        self.body = body
        self.code = code
        self.url = updates.UPDATE_URL if url is None else url
        self.read_sizes = []
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.closed = True

    def getcode(self):
        return self.code

    def geturl(self):
        return self.url

    def read(self, size):
        self.read_sizes.append(size)
        return self.body[:size]


class Opener:
    def __init__(self, response=None, error=None):
        self.response = response or Response()
        self.error = error
        self.calls = []

    def open(self, request, timeout):
        self.calls.append((request, timeout))
        if self.error:
            raise self.error
        return self.response


class ProcessOutput:
    def __init__(self, body, blocked=False):
        self.body = body
        self.blocked = blocked
        self.released = threading.Event()
        self.read_sizes = []
        self.closed = False

    def read(self, size):
        self.read_sizes.append(size)
        if self.blocked:
            self.released.wait(timeout=2)
        return self.body[:size]

    def close(self):
        self.closed = True


class Process:
    def __init__(self, body=b"0.2.0\n", exit_code=0, blocked=False, wait_timeout=False):
        self.stdout = ProcessOutput(body, blocked)
        self.exit_code = exit_code
        self.wait_timeout = wait_timeout
        self.returncode = None
        self.killed = False
        self.waits = []

    def poll(self):
        return self.returncode

    def wait(self, timeout):
        self.waits.append(timeout)
        if self.wait_timeout and not self.killed:
            raise updates.subprocess.TimeoutExpired("fixture-gh", timeout)
        self.returncode = -9 if self.killed else self.exit_code
        return self.returncode

    def kill(self):
        self.killed = True
        self.returncode = -9
        self.stdout.released.set()


class UpdateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="shippykit-updates-test-")
        self.root = Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)
        (self.root / ".shippykit").mkdir()
        self.receipt = self.root / ".shippykit/install.json"
        self.install("0.1.0")

    def install(self, version, **extra):
        self.receipt.write_text(json.dumps({"schema_version": 1, "package_version": version, "conflicts": [], **extra}), encoding="utf-8")

    def private_opener(self, code=404, url=None):
        return Opener(error=urllib.error.HTTPError(url or updates.UPDATE_URL, code, "PRIVATE_ERROR", {}, None))

    def check_with_process(self, process):
        with mock.patch.object(updates.shutil, "which", return_value="/fixture/gh"), mock.patch.object(updates.subprocess, "Popen", return_value=process) as launch:
            result = updates.check_updates(self.root, self.private_opener())
        return result, launch

    def test_newer_notification_is_advisory_and_does_not_change_project(self):
        (self.root / "STATE.md").write_text("Preserve owner decision", encoding="utf-8")
        before = {str(p.relative_to(self.root)): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        opener = Opener()
        result = updates.check_updates(self.root, opener)
        self.assertEqual(result["status"], "update_available")
        self.assertEqual(result["installed_version"], "0.1.0")
        self.assertEqual(result["latest_version"], "0.2.0")
        self.assertFalse(result["automatic_update"])
        self.assertEqual(before, {str(p.relative_to(self.root)): p.read_bytes() for p in self.root.rglob("*") if p.is_file()})
        self.assertNotIn(str(self.root), json.dumps(result))
        self.assertTrue(opener.response.closed)

    def test_fixed_https_request_has_no_auth_or_project_identity_and_is_bounded(self):
        opener = Opener()
        updates.check_updates(self.root, opener)
        self.assertEqual(len(opener.calls), 1)
        request, timeout = opener.calls[0]
        self.assertEqual(request.full_url, "https://raw.githubusercontent.com/jamesktan/shippykit/main/docs/launch/harness/VERSION")
        self.assertEqual(request.get_method(), "GET")
        self.assertEqual(timeout, 5)
        self.assertIsNone(request.get_header("Authorization"))
        self.assertIsNone(request.data)
        self.assertEqual(opener.response.read_sizes, [257])

    def test_default_opener_disables_proxies_and_redirects(self):
        opener = Opener()
        with mock.patch.object(updates.urllib.request, "build_opener", return_value=opener) as build:
            updates.check_updates(self.root)
        handlers = build.call_args.args
        self.assertEqual(handlers[0].proxies, {})
        self.assertIsInstance(handlers[1], updates.NoUpdateRedirect)
        self.assertIsNone(handlers[1].redirect_request(None, None, 302, "redirect", {}, "http://evil.invalid/"))

    def test_private_source_uses_fixed_existing_gh_access_without_prompt_or_shell(self):
        process = Process()
        with mock.patch.dict(updates.os.environ, {"GH_DEBUG": "api", "DEBUG": "true", "GH_HOST": "evil.invalid", "GH_TOKEN": "SECRET_TOKEN", "HTTPS_PROXY": "http://SECRET_PROXY", "GH_HTTP_UNIX_SOCKET": "/SECRET_SOCKET"}):
            result, launch = self.check_with_process(process)
        self.assertEqual(result["status"], "update_available")
        self.assertEqual(result["transport"], "existing_github_cli")
        self.assertEqual(result["source_url"], "https://api.github.com/repos/jamesktan/shippykit/contents/docs/launch/harness/VERSION?ref=main")
        self.assertEqual(launch.call_args.args[0], ["/fixture/gh", "api", "--hostname", "github.com", "--method", "GET", "repos/jamesktan/shippykit/contents/docs/launch/harness/VERSION?ref=main", "--header", "Accept:application/vnd.github.raw+json"])
        options = launch.call_args.kwargs
        self.assertFalse(options["shell"])
        self.assertEqual(options["stdin"], updates.subprocess.DEVNULL)
        self.assertEqual(options["stderr"], updates.subprocess.DEVNULL)
        self.assertEqual(options["env"]["GH_HOST"], "github.com")
        self.assertEqual(options["env"]["GH_PROMPT_DISABLED"], "1")
        self.assertEqual(options["env"]["GH_NO_UPDATE_NOTIFIER"], "1")
        for key in ("GH_DEBUG", "DEBUG", "HTTPS_PROXY", "GH_HTTP_UNIX_SOCKET"):
            self.assertNotIn(key, options["env"])
        self.assertEqual(process.stdout.read_sizes, [257])
        self.assertTrue(process.stdout.closed)
        self.assertFalse(process.killed)
        self.assertLessEqual(process.waits[0], 5)
        self.assertNotIn("SECRET", json.dumps(result))
        self.assertNotIn(str(self.root), json.dumps(result))
        self.assertIn("existing GitHub CLI access", updates.updates_text(result))

    def test_fallback_only_for_fixed_origin_access_statuses(self):
        with mock.patch.object(updates, "github_cli_version", return_value=(b"0.2.0\n", None)) as fallback:
            for code in (401, 403, 404):
                self.assertEqual(updates.check_updates(self.root, self.private_opener(code))["status"], "update_available")
            self.assertEqual(fallback.call_count, 3)
            fallback.reset_mock()
            for opener in [self.private_opener(500), self.private_opener(302), self.private_opener(404, "https://evil.invalid/VERSION"), Opener(error=TimeoutError()), Opener(error=urllib.error.URLError("offline")), Opener()]:
                updates.check_updates(self.root, opener)
            fallback.assert_not_called()

    def test_access_error_body_is_closed_without_reading(self):
        body = io.BytesIO(b"SECRET_PRIVATE_ERROR")
        error = urllib.error.HTTPError(updates.UPDATE_URL, 404, "private", {}, body)
        with mock.patch.object(updates, "github_cli_version", return_value=(b"0.2.0\n", None)):
            result = updates.check_updates(self.root, Opener(error=error))
        self.assertTrue(body.closed)
        self.assertEqual(result["status"], "update_available")
        self.assertNotIn("SECRET", json.dumps(result))

    def test_missing_cli_and_failed_launch_remain_unavailable(self):
        with mock.patch.object(updates.shutil, "which", return_value=None), mock.patch.object(updates.subprocess, "Popen") as launch:
            result = updates.check_updates(self.root, self.private_opener())
            self.assertEqual(result["reason"], "github_cli_unavailable")
            launch.assert_not_called()
        with mock.patch.object(updates.shutil, "which", return_value="/fixture/gh"), mock.patch.object(updates.subprocess, "Popen", side_effect=OSError("SECRET_PATH")):
            result = updates.check_updates(self.root, self.private_opener())
            self.assertEqual(result["status"], "unavailable")
            self.assertNotIn("SECRET", json.dumps(result))

    def test_cli_nonzero_or_invalid_output_is_not_current(self):
        result, _ = self.check_with_process(Process(exit_code=1))
        self.assertEqual(result["reason"], "github_cli_access_unavailable")
        self.assertEqual(result["status"], "unavailable")
        result, _ = self.check_with_process(Process(body=b"SECRET_HTML"))
        self.assertEqual(result["reason"], "invalid_latest_version")
        self.assertNotIn("SECRET", json.dumps(result))

    def test_cli_oversized_output_is_bounded_and_process_reaped(self):
        process = Process(body=b"x" * 100000)
        result, _ = self.check_with_process(process)
        self.assertEqual(result["reason"], "version_response_too_large")
        self.assertEqual(process.stdout.read_sizes, [257])
        self.assertTrue(process.killed)
        self.assertTrue(process.stdout.closed)
        self.assertIsNotNone(process.poll())
        self.assertEqual(process.waits, [1])

    def test_cli_timeout_during_read_or_exit_kills_and_reaps_process(self):
        for process in (Process(blocked=True), Process(wait_timeout=True)):
            with mock.patch.object(updates, "UPDATE_TIMEOUT_SECONDS", 0.02):
                result, _ = self.check_with_process(process)
            self.assertEqual(result["reason"], "github_cli_timeout")
            self.assertEqual(result["status"], "unavailable")
            self.assertTrue(process.killed)
            self.assertTrue(process.stdout.closed)
            self.assertIsNotNone(process.poll())
            self.assertEqual(process.waits[-1], 1)

    def test_canonical_semver_prerelease_order_and_numeric_comparison(self):
        ordered = ["1.0.0-alpha", "1.0.0-alpha.1", "1.0.0-alpha.beta", "1.0.0-beta", "1.0.0-beta.2", "1.0.0-beta.11", "1.0.0-rc.1", "1.0.0", "1.0.1", "1.1.0", "1.10.0", "2.0.0"]
        for first, second in zip(ordered, ordered[1:]):
            self.assertEqual(updates.compare_semver(first, second), -1, (first, second))
            self.assertEqual(updates.compare_semver(second, first), 1, (first, second))
        self.assertEqual(updates.compare_semver("1.0.0+build.009", "1.0.0+other"), 0)
        self.assertEqual(updates.compare_semver("1.0.0-alpha+first", "1.0.0-alpha+second"), 0)
        self.assertEqual(updates.compare_semver("1.0.0-9", "1.0.0-a"), -1)

    def test_same_ahead_and_prerelease_results(self):
        for installed, published, expected in [("1.0.0", "1.0.0+rebuilt", "up_to_date"), ("2.0.0", "1.9.0", "installed_ahead"), ("1.0.0-beta.2", "1.0.0-beta.11", "update_available"), ("1.0.0", "1.0.0-rc.9", "installed_ahead")]:
            self.install(installed)
            result = updates.check_updates(self.root, Opener(Response(published.encode())))
            self.assertEqual(result["status"], expected)

    def test_strict_versions_reject_malformed_text_without_echo(self):
        for version in ["1.2", "01.2.3", "1.02.3", "1.2.03", "1.2.3-01", "1.2.3-a..b", "1.2.3+", "v1.2.3", " 1.2.3", "1.2.3\nSECRET_PAYLOAD", "1.2.3-\u0661", "x" * 129]:
            with self.subTest(version=version):
                result = updates.check_updates(self.root, Opener(Response(version.encode())))
                self.assertEqual(result["status"], "unavailable")
                self.assertEqual(result["reason"], "invalid_latest_version")
                self.assertNotIn("SECRET_PAYLOAD", json.dumps(result))
        self.assertEqual(updates.parse_semver("0.0.0-0+001")[0], (0, 0, 0))

    def test_network_failure_timeout_and_unexpected_origin_never_report_up_to_date(self):
        for error in [TimeoutError("SECRET_TIMEOUT"), urllib.error.URLError("SECRET_PROXY"), OSError("SECRET_PATH")]:
            result = updates.check_updates(self.root, Opener(error=error))
            self.assertEqual(result["status"], "unavailable")
            self.assertEqual(result["reason"], "update_source_unavailable")
            self.assertNotIn("SECRET", json.dumps(result))
        result = updates.check_updates(self.root, Opener(Response(url="https://evil.invalid/VERSION")))
        self.assertEqual(result["reason"], "unexpected_update_response")
        self.assertEqual(updates.check_updates(self.root, Opener(Response(code=503)))["status"], "unavailable")

    def test_oversized_response_read_is_capped(self):
        response = Response(b"x" * 100000)
        result = updates.check_updates(self.root, Opener(response))
        self.assertEqual(result["reason"], "version_response_too_large")
        self.assertEqual(response.read_sizes, [257])
        self.assertTrue(response.closed)

    def test_interrupted_or_malformed_http_response_is_unavailable_and_closed(self):
        for error in [http.client.IncompleteRead(b"SECRET_PARTIAL", 10), http.client.BadStatusLine("SECRET_STATUS")]:
            response = Response()
            with mock.patch.object(response, "read", side_effect=error):
                result = updates.check_updates(self.root, Opener(response))
            self.assertEqual(result["status"], "unavailable")
            self.assertEqual(result["reason"], "update_source_unavailable")
            self.assertIsNone(result["latest_version"])
            self.assertTrue(response.closed)
            self.assertNotIn("SECRET", json.dumps(result))

    def test_invalid_missing_oversized_receipt_avoids_network(self):
        for value in ["not-json", "[]", '{"schema_version":2,"package_version":"0.1.0"}', '{"schema_version":1,"package_version":"01.1.0"}', '{"schema_version":1}', "x" * (updates.MAX_JSON_BYTES + 1)]:
            self.receipt.write_text(value, encoding="utf-8")
            opener = Opener()
            result = updates.check_updates(self.root, opener)
            self.assertEqual(result["status"], "unavailable")
            self.assertEqual(result["reason"], "installation_receipt_missing_or_invalid")
            self.assertFalse(opener.calls)
        self.receipt.unlink()
        self.assertEqual(updates.check_updates(self.root, Opener())["status"], "unavailable")

    def test_symlink_receipt_or_directory_is_not_read(self):
        outside = self.root / "outside.json"
        outside.write_text(self.receipt.read_text(), encoding="utf-8")
        self.receipt.unlink()
        self.receipt.symlink_to(outside)
        opener = Opener()
        self.assertEqual(updates.check_updates(self.root, opener)["status"], "unavailable")
        self.assertFalse(opener.calls)
        self.receipt.unlink()
        (self.root / ".shippykit").rmdir()
        target = self.root / "external"
        target.mkdir()
        (self.root / ".shippykit").symlink_to(target, target_is_directory=True)
        (target / "install.json").write_text(outside.read_text(), encoding="utf-8")
        self.assertEqual(updates.check_updates(self.root, opener)["status"], "unavailable")
        self.assertFalse(opener.calls)

    def test_conflicted_receipt_does_not_claim_all_managed_files_updated(self):
        self.install("0.2.0", conflicts=[{"path": "deploy/helper.py", "private": "SECRET"}])
        result = updates.check_updates(self.root, Opener())
        self.assertEqual(result["status"], "up_to_date")
        self.assertEqual(result["unresolved_conflicts"], 1)
        self.assertIn("unresolved", updates.updates_text(result))
        self.assertNotIn("SECRET", json.dumps(result))

    def test_cli_unavailable_is_nonblocking_and_status_never_checks_updates(self):
        output = io.StringIO()
        with mock.patch.object(updates, "check_updates", return_value={"status": "unavailable", "reason": "test_offline"}) as check, contextlib.redirect_stdout(output):
            self.assertEqual(updates.main(["updates", "--project", str(self.root), "--json"]), 0)
            check.assert_called_once()
        with mock.patch.object(updates, "check_updates", side_effect=AssertionError("status must stay offline")), mock.patch.object(updates, "git_summary", return_value={"state": "unverified"}), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(updates.main(["status", "--project", str(self.root), "--json"]), 0)
        self.assertIn("unavailable", output.getvalue())


if __name__ == "__main__":
    unittest.main()
