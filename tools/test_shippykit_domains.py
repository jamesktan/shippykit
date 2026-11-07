"""No network, Railway, DNS or desktop access: domains.py runs against scripted fakes.

The fake Squarespace dashboard renders accessibility trees in the format Cua Driver returned
for the real pages on 2026-10-29 (DNS settings, custom records, Website tab, verify dialog).
"""
import contextlib
import datetime
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True
HELPER = Path(__file__).resolve().parents[1] / "docs/launch/harness/deploy/domains.py"
SPEC = importlib.util.spec_from_file_location("shippykit_domains", HELPER)
domains = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(domains)

DOMAIN, HOST, TARGET = "example.games", "www.example.games", "abcd1234.up.railway.app"
TOKEN = "railway-verify=" + "f0" * 32
NS = ["nsc1.squarespacedns.com", "nsc2.squarespacedns.com"]
RW = {"project": "proj-1", "service": "example-site", "environment": "production", "port": 8080}


class FakeChrome:
    """A Squarespace dashboard in one Chrome process, driven through `cua-driver call`."""

    def __init__(self, presets=("Squarespace Defaults", "Email Security"), records=(), rules=(), verify_on=(), locked=False):
        self.presets, self.records, self.rules = list(presets), [dict(r) for r in records], [dict(r) for r in rules]
        self.verify_on, self.verified, self.verify_active, self.verify_snaps = set(verify_on), False, False, 0
        self.locked, self.windows, self.snap_no, self.tokens = locked, {1: {"url": "about:other", "page": "other"}}, 0, {}
        self.form = self.fwd = None
        self.notice, self.mutations = False, []

    # rendering ---------------------------------------------------------
    def title(self, win):
        page = self.windows[win]["page"]
        return {"dns": f"Squarespace Domains — {DOMAIN} — DNS Settings", "website": f"Squarespace Domains — {DOMAIN} — Website"}.get(page, "Other window")

    def render(self, win):
        self.snap_no += 1
        snap, lines, row = f"s{self.snap_no}", [], [0]

        def add(text, action=None, depth=1):
            row[0] += 1
            lines.append("  " * depth + f"- [{row[0]}] {text}")
            if action:
                self.tokens[f"{snap}:{row[0]}"] = action

        w = self.windows[win]
        add(f'AXTextField "Address and search bar" = "{w["url"]}" [actions=[press]]', ("address", win))
        add(f'AXWebArea "{self.title(win)}"')
        if w["page"] == "dns":
            add('AXHeading "DNS Presets"', depth=2)
            for name in self.presets:
                add(f'AXStaticText = "{name}"', depth=3)
                add(f'AXButton "Delete preset {name}" [actions=[press]]', ("delete_preset", name), 3)
                add('AXStaticText = "CNAME"', depth=4)
                add('AXStaticText = "www"', depth=4)
                add('AXStaticText = "N/A"', depth=4)
                add('AXStaticText = "4 hrs"', depth=4)
                add('AXStaticText = "ext-sq.squarespace.com"', depth=4)
            add('AXHeading "Custom records"', depth=2)
            add('AXButton "ADD RECORD" [actions=[press]]', ("add_record",), 2)
            if self.form is not None:
                add('AXHeading "Add Record"', depth=2)
                add('AXButton "save record" [actions=[press]]', ("save_record",), 2)
                add(f'AXComboBox "TYPE" = "{self.form["type"] or "Type"}" [actions=[press]]', ("type_menu",), 2)
                if self.form["menu"]:
                    for kind in ("A", "CNAME", "TXT"):
                        add(f'AXStaticText = "{kind}" [actions=[press]]', ("type", kind), 3)
                add(f'AXTextField "NAME"{self.shown(self.form["name"])} [actions=[press]]', ("field", "name"), 2)
                label = "TEXT" if self.form["type"] == "TXT" else "DATA"
                add(f'AXTextField "{label}"{self.shown(self.form["value"])} [actions=[press]]', ("field", "value"), 2)
            for label in ("TYPE", "NAME", "PRIORITY", "TTL", "DATA"):
                add(f'AXStaticText = "{label}"', depth=3)
            for r in self.records:
                for value in (r["type"], r["name"], "N/A", "4 hrs", r["value"]):
                    add(f'AXStaticText = "{value}"', depth=4)
        elif w["page"] == "website":
            add('AXHeading "Domain forwarding"', depth=2)
            add('AXButton "Add domain forwarding url" [actions=[press]]', ("add_forwarding",), 2)
            for rule in self.rules:
                for value in ("FROM", "TO", rule["to"], "REDIRECT TYPE", rule["type"], "PATH FORWARDING", rule["paths"], "LAST UPDATED", "Oct 29, 2026"):
                    add(f'AXStaticText = "{value}"', depth=3)
            if self.fwd is not None:
                add(f'AXTextField "SUBDOMAIN"{self.shown(self.fwd["sub"])} [actions=[press]]', ("fwd_field", "sub"), 2)
                add(f'AXTextField "ENTER WEBSITE URL"{self.shown(self.fwd["url"])} [actions=[press]]', ("fwd_field", "url"), 2)
                add('AXButton "Advanced settings" [actions=[press]]', ("advanced",), 2)
                if self.fwd["advanced"]:
                    for label in ("Temporary Redirect (302)", "Permanent Redirect (301)", "Remove paths", "Maintain paths"):
                        add(f'AXRadioButton "{label}" [actions=[press]]', ("radio", label), 3)
                add('AXButton "SAVE" [actions=[press]]', ("save_forwarding",), 2)
            if self.notice:
                add('AXHeading "Domain forwarding rule has been created"', depth=2)
                add('AXButton "OKAY" [actions=[press]]', ("okay",), 2)
        if self.verify_active:
            add('AXWebArea "Squarespace — Login"', depth=1)
            add('AXStaticText = "Verify to continue as owner@example.com"', depth=2)
            add('AXButton "CONTINUE" [actions=[press]]', ("continue",), 2)
        add('AXPopUpButton "Tab search" [actions=[press]]', depth=0)
        add(f'AXRadioButton "{self.title(win)} - Memory usage - 200 MB" [actions=[press]]', depth=1)
        add('AXButton "Close" [actions=[press]]', ("close_tab", win), 2)
        return {"snapshot_id": snap, "window_title": self.title(win), "tree_markdown": "\n".join(lines), "element_count": row[0]}

    @staticmethod
    def shown(value):
        return f' = "{value}"' if value else ""

    # driver ------------------------------------------------------------
    def open(self, url):
        win = max(self.windows) + 1
        self.windows[win] = {"url": url, "page": self.page_for(url)}

    @staticmethod
    def page_for(url):
        return "dns" if url.endswith("/dns/dns-settings") else "website" if url.endswith("/website") else "other"

    def needs_verify(self, action):
        if action in self.verify_on and not self.verified:
            self.verify_active, self.verify_snaps = True, 2
            return True
        return False

    def call(self, tool, args):
        if tool == "list_windows":
            return {"windows": [{"pid": 620, "window_id": w, "title": self.title(w), "is_on_screen": True} for w in self.windows]}
        if tool == "get_window_state":
            if self.locked:
                return {"degraded_reason": "screen_locked: no accessibility tree", "element_count": 0, "tree_markdown": ""}
            if self.verify_active:
                self.verify_snaps -= 1
                if self.verify_snaps < 0:
                    self.verify_active, self.verified = False, True
            return self.render(args["window_id"])
        if tool == "end_session":
            return {"active": False}
        action = self.tokens.get(args.get("element_token"))
        assert action, f"stale or unknown token for {tool}: {args}"
        if tool == "set_value":
            kind = action[0]
            if kind == "address":
                self.windows[action[1]]["url"] = args["value"]
            elif kind == "field":
                self.form[action[1]] = args["value"]
            elif kind == "fwd_field":
                self.fwd[action[1]] = args["value"]
            return {"effect": "unverifiable"}
        if tool == "press_key":
            assert action[0] == "address" and args["key"] == "return"
            w = self.windows[action[1]]
            w["page"] = self.page_for(w["url"])
            self.form = self.fwd = None
            return {"effect": "confirmed"}
        assert tool == "click", tool
        self.click(action)
        return {"effect": "unverifiable", "summary": "pressed"}

    def click(self, action):
        kind = action[0]
        if kind == "delete_preset":
            if not self.needs_verify("delete_preset"):
                self.presets.remove(action[1])
                self.mutations.append(action)
        elif kind == "add_record":
            self.form = {"type": "", "name": "", "value": "", "menu": False}
        elif kind == "type_menu":
            self.form["menu"] = True
        elif kind == "type":
            self.form.update(type=action[1], menu=False)
        elif kind == "save_record":
            self.records.append({"type": self.form["type"], "name": self.form["name"], "value": self.form["value"]})
            self.mutations.append(("record", self.form["type"], self.form["name"]))
            self.form = None
        elif kind == "add_forwarding":
            if not self.needs_verify("forwarding"):
                self.fwd = {"sub": "", "url": "", "advanced": False, "radios": set()}
        elif kind == "advanced":
            self.fwd["advanced"] = True
        elif kind == "radio":
            self.fwd["radios"].add(action[1])
        elif kind == "save_forwarding":
            permanent = "Permanent Redirect (301)" in self.fwd["radios"]
            keep = "Maintain paths" in self.fwd["radios"]
            self.rules.append({"to": self.fwd["url"], "type": "Permanent redirect" if permanent else "Temporary redirect", "paths": "Forward path" if keep else "Remove path"})
            self.mutations.append(("forwarding", self.fwd["sub"], self.fwd["url"]))
            self.fwd, self.notice = None, True
        elif kind == "okay":
            self.notice = False
        elif kind == "close_tab":
            del self.windows[action[1]]


class FakeEnv:
    def __init__(self, chrome=None, sessions=(), railway=None, dig=None, curl=None, tools=("railway", "dig", "curl", "cua-driver")):
        self.chrome, self.sessions, self.tools = chrome, list(sessions), set(tools)
        self.railway = railway if railway is not None else Railway()
        self.dig_answers = dig or {}
        self.curl_answers = curl or {}
        self.clock, self.notices, self.calls = 1_800_000_000.0, [], []

    def which(self, name):
        return f"/usr/local/bin/{name}" if name in self.tools else None

    def sleep(self, seconds):
        self.clock += seconds

    def now(self):
        return self.clock

    def notify(self, message):
        self.notices.append(message)

    def run(self, cmd, timeout=60):
        self.calls.append(cmd)
        name = Path(cmd[0]).name
        if name == "railway":
            return self.railway.run(cmd[1:])
        if name == "dig":
            target, rtype = cmd[4], cmd[5]
            server = cmd[6][1:] if len(cmd) > 6 else None
            values = self.dig_answers.get((target, rtype, server), self.dig_answers.get((target, rtype), []))
            return 0, "\n".join(values) + "\n", ""
        if name == "curl":
            url = cmd[-1]
            if "-w" not in cmd:  # a page fetch returns the body
                return 0, self.curl_answers.get("body:" + url, f'<link rel="canonical" href="https://{HOST}/">'), ""
            default = f"301 https://{HOST}{domains.REDIRECT_PROBE}" if url.endswith(domains.REDIRECT_PROBE) else "200 "
            return 0, self.curl_answers.get(url, default), ""
        if name == "cua-driver":
            if cmd[1] == "sessions":
                return 0, json.dumps({"sessions": self.sessions}), ""
            return 0, json.dumps(self.chrome.call(cmd[2], json.loads(cmd[3]))), ""
        if name == "open":
            self.chrome.open(cmd[-1])
            return 0, "", ""
        raise AssertionError(f"unexpected command {cmd}")


class Railway:
    def __init__(self, logged_in=True, domains=(HOST,), verified=True, certificate="CERTIFICATE_STATUS_TYPE_VALID"):
        self.logged_in, self.domains, self.verified, self.certificate = logged_in, list(domains), verified, certificate
        self.created = []

    def run(self, args):
        if args[0] == "whoami":
            return (0, json.dumps({"name": "Owner"}), "") if self.logged_in else (1, "", "Unauthorized. Please login with `railway login`")
        if args[:2] == ["domain", "list"]:
            return 0, json.dumps({"domains": [{"domain": d} for d in self.domains]}), ""
        if args[:2] == ["domain", "status"]:
            return 0, json.dumps({"domain": {
                "id": "dom-1", "dnsRecords": [{"recordType": "DNS_RECORD_TYPE_CNAME", "requiredValue": TARGET, "currentValue": "stale.example"}],
                "verification": {"verified": self.verified, "dnsHost": "_railway-verify.www", "token": TOKEN},
                "certificate": {"status": self.certificate}}}), ""
        if args[0] == "domain":
            self.created.append(args[1])
            self.domains.append(args[1])
            return 0, json.dumps({"customDomainCreate": {"domain": args[1]}}), ""
        if args[0] == "list":
            return 0, json.dumps([{"workspace": {"name": "Personal"}, "id": "proj-1", "name": "example-website",
                                   "services": {"edges": [{"node": {"name": "example-site"}}, {"node": {"name": "Postgres"}}]},
                                   "environments": {"edges": [{"node": {"name": "production"}}]}}]), ""
        raise AssertionError(f"unexpected railway {args}")


def live_dns(cname=True, txt=True, public=True):
    answers = {(DOMAIN, "NS", "1.1.1.1"): NS, (TARGET, "A", "1.1.1.1"): ["66.33.22.11"]}
    answers[(HOST, "CNAME", NS[0])] = [TARGET] if cname else ["ext-sq.squarespace.com"]
    answers[(f"_railway-verify.www.{DOMAIN}", "TXT", NS[0])] = [f'"{TOKEN}"'] if txt else []
    for r in domains.PUBLIC_RESOLVERS:
        answers[(HOST, "CNAME", r)] = [TARGET] if public else []
    return answers


def run_cli(env, *argv):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = domains.main(list(argv), env)
    return code, out.getvalue()


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        self.addCleanup(self.tmp.cleanup)

    def seed(self, records=True, events=()):
        state = domains.load_state(self.root, DOMAIN)
        state["railway"] = dict(RW)
        if records:
            state["records"] = [{"type": "CNAME", "name": "www", "value": TARGET}, {"type": "TXT", "name": "_railway-verify.www", "value": TOKEN}]
        state["events"] = list(events)
        path = domains.state_path(self.root, DOMAIN)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(state))

    def env(self, **kw):
        return FakeEnv(**kw)


class PageModelTests(Base):
    def test_custom_records_ignore_presets_headers_and_dropdown_options(self):
        chrome = FakeChrome(records=[{"type": "CNAME", "name": "www", "value": TARGET}])
        chrome.windows[2] = {"url": "x/dns/dns-settings", "page": "dns"}
        chrome.form = {"type": "TXT", "name": "", "value": "", "menu": True}
        tree = chrome.render(2)["tree_markdown"]
        self.assertEqual(domains.custom_records(tree), [{"type": "CNAME", "name": "www", "value": TARGET}])
        self.assertEqual(domains.presets(tree), ["Squarespace Defaults", "Email Security"])

    def test_forwarding_rule_states(self):
        chrome = FakeChrome(rules=[{"to": f"https://{HOST}", "type": "Permanent redirect", "paths": "Forward path"}])
        chrome.windows[2] = {"url": "x/website", "page": "website"}
        self.assertEqual(domains.rule_state(domains.forwarding_rules(chrome.render(2)["tree_markdown"]), DOMAIN), "ok")
        chrome.rules = [{"to": f"https://{HOST}/", "type": "Temporary redirect", "paths": "Forward path"}]
        self.assertEqual(domains.rule_state(domains.forwarding_rules(chrome.render(2)["tree_markdown"]), DOMAIN), "wrong")
        chrome.rules = []
        self.assertEqual(domains.rule_state(domains.forwarding_rules(chrome.render(2)["tree_markdown"]), DOMAIN), "missing")

    def test_conflicts_only_for_the_same_name(self):
        wanted = [{"type": "CNAME", "name": "www", "value": TARGET}]
        self.assertEqual(domains.conflicts([{"type": "A", "name": "www", "value": "1.2.3.4"}], wanted), [{"type": "A", "name": "www", "value": "1.2.3.4"}])
        self.assertEqual(domains.conflicts([{"type": "CNAME", "name": "www", "value": TARGET + "."}], wanted), [])
        self.assertEqual(domains.conflicts([{"type": "A", "name": "@", "value": "1.2.3.4"}], wanted), [])

    def test_rejects_www_and_junk(self):
        for bad in ("www.example.com", "not a domain", "example"):
            with self.assertRaises(SystemExit):
                domains.check_domain(bad)
        self.assertEqual(domains.check_domain(" Example.COM. "), "example.com")


class StatusTests(Base):
    def status(self, env, *extra):
        code, out = run_cli(env, "status", "--domain", DOMAIN, "--root", self.root, *extra)
        return code, out, out.strip().splitlines()[-2:]

    def test_everything_live_is_done(self):
        self.seed()
        code, out, _ = self.status(self.env(dig=live_dns()))
        self.assertEqual(code, domains.EXIT_DONE, out)
        self.assertIn("NEXT [done]", out)
        self.assertNotIn("missing", out)

    def test_first_run_fills_in_the_matching_project_and_web_service(self):
        code, out, _ = self.status(self.env(dig=live_dns()))
        self.assertEqual(code, domains.EXIT_NEXT)
        self.assertIn(f"$ python3 deploy/domains.py railway --domain {DOMAIN} --project proj-1 --service example-site", out)

    def test_first_run_without_a_clear_match_lists_projects(self):
        code, out = run_cli(self.env(), "status", "--domain", "unrelated.games", "--root", self.root)
        self.assertEqual(code, domains.EXIT_NEXT)
        self.assertIn("domains.py projects", out)
        self.assertIn("<project-id>", out)

    def test_signed_out_railway_is_an_owner_step(self):
        self.seed()
        code, out, _ = self.status(self.env(railway=Railway(logged_in=False), dig=live_dns()))
        self.assertEqual(code, domains.EXIT_OWNER)
        self.assertIn("railway login", out)

    def test_missing_domain_points_to_the_railway_step(self):
        self.seed()
        code, out, _ = self.status(self.env(railway=Railway(domains=()), dig=live_dns()))
        self.assertIn(f"domains.py railway --domain {DOMAIN}", out)

    def test_unpublished_domain_waits(self):
        self.seed()
        dns = live_dns()
        dns[(DOMAIN, "NS", "1.1.1.1")] = []
        code, out, _ = self.status(self.env(dig=dns))
        self.assertIn("NEXT [wait]", out)

    def test_other_dns_host_lists_records_for_the_owner(self):
        self.seed()
        dns = live_dns()
        dns[(DOMAIN, "NS", "1.1.1.1")] = ["ns1.cloudflare.com"]
        code, out, _ = self.status(self.env(dig=dns))
        self.assertEqual(code, domains.EXIT_OWNER)
        self.assertIn(f"CNAME www → {TARGET}", out)

    def test_missing_squarespace_records_point_to_the_squarespace_step(self):
        self.seed()
        code, out, _ = self.status(self.env(railway=Railway(verified=False), dig=live_dns(cname=False, txt=False, public=False)))
        self.assertIn(f"domains.py squarespace --domain {DOMAIN}", out)

    def test_records_at_squarespace_but_not_public_yet_wait(self):
        self.seed()
        code, out, _ = self.status(self.env(dig=live_dns(public=False)))
        self.assertIn("NEXT [wait]", out)
        self.assertIn("public DNS", out)

    def test_temporary_or_path_dropping_redirect_is_reported(self):
        self.seed()
        env = self.env(dig=live_dns(), curl={f"http://{DOMAIN}{domains.REDIRECT_PROBE}": f"302 https://{HOST}{domains.REDIRECT_PROBE}"})
        code, out, _ = self.status(env)
        self.assertEqual(code, domains.EXIT_OWNER)
        self.assertIn("temporary redirect", out)

    def test_new_forwarding_rule_waits_instead_of_reapplying(self):
        created = datetime.datetime.fromtimestamp(1_800_000_000 - 3600, datetime.timezone.utc).isoformat()
        self.seed(events=[{"at": created, "event": "forwarding_created"}])
        env = self.env(dig=live_dns(), curl={f"http://{DOMAIN}{domains.REDIRECT_PROBE}": "200 "})
        code, out, _ = self.status(env)
        self.assertIn("NEXT [wait]", out)
        self.assertIn("48 hours", out)

    def test_old_canonical_address_is_flagged(self):
        self.seed()
        env = self.env(dig=live_dns(), curl={f"body:https://{HOST}/": '<link rel="canonical" href="https://old.up.railway.app/">'})
        code, out, _ = self.status(env)
        self.assertIn("PUBLIC_ORIGIN", out)

    def test_status_writes_nothing_without_new_settings(self):
        self.status(self.env(dig=live_dns()))
        self.assertFalse(domains.state_path(self.root, DOMAIN).exists())


class RailwayTests(Base):
    def test_projects_lists_services(self):
        code, out = run_cli(self.env(), "projects")
        self.assertEqual(code, 0)
        self.assertIn("example-website | project proj-1 | web: example-site | all services: example-site, Postgres", out)

    def test_adds_missing_domain_once_and_saves_records(self):
        railway = Railway(domains=())
        env = self.env(railway=railway)
        args = ("railway", "--domain", DOMAIN, "--root", self.root, "--project", "proj-1", "--service", "example-site")
        self.assertEqual(run_cli(env, *args)[0], 0)
        self.assertEqual(railway.created, [HOST])
        state = json.loads(domains.state_path(self.root, DOMAIN).read_text())
        self.assertEqual(state["records"][0], {"type": "CNAME", "name": "www", "value": TARGET})
        self.assertEqual(state["railway"]["service"], "example-site")
        self.assertEqual(run_cli(env, "railway", "--domain", DOMAIN, "--root", self.root)[0], 0)
        self.assertEqual(railway.created, [HOST], "second run must not add the domain again")

    def test_requires_project_and_service(self):
        code, out = run_cli(self.env(), "railway", "--domain", DOMAIN, "--root", self.root)
        self.assertEqual(code, domains.EXIT_ERROR)
        self.assertIn("domains.py projects", out)


class SquarespaceTests(Base):
    def apply(self, env, *extra):
        return run_cli(env, "squarespace", "--domain", DOMAIN, "--root", self.root, *extra)

    def test_applies_everything_then_a_rerun_changes_nothing(self):
        self.seed()
        chrome = FakeChrome()
        env = self.env(chrome=chrome)
        code, out = self.apply(env)
        self.assertEqual(code, 0, out)
        self.assertNotIn("Squarespace Defaults", chrome.presets)
        self.assertIn("Email Security", chrome.presets)
        self.assertEqual({(r["type"], r["name"], r["value"]) for r in chrome.records},
                         {("CNAME", "www", TARGET), ("TXT", "_railway-verify.www", TOKEN)})
        self.assertEqual(chrome.rules, [{"to": f"https://{HOST}", "type": "Permanent redirect", "paths": "Forward path"}])
        self.assertEqual(list(chrome.windows), [1], "the helper closes only its own window")
        state = json.loads(domains.state_path(self.root, DOMAIN).read_text())
        self.assertIn("forwarding_created", [e["event"] for e in state["events"]])
        before = len(chrome.mutations)
        code, out = self.apply(env)
        self.assertEqual(code, 0, out)
        self.assertEqual(len(chrome.mutations), before)
        self.assertIn("nothing needed changing", out)

    def test_dry_run_lists_changes_without_making_them(self):
        self.seed()
        chrome = FakeChrome()
        code, out = self.apply(self.env(chrome=chrome), "--dry-run")
        self.assertEqual(code, domains.EXIT_NEXT)
        self.assertIn("delete preset Squarespace Defaults", out)
        self.assertIn(f"add CNAME www → {TARGET}", out)
        self.assertIn("add redirect", out)
        self.assertEqual(chrome.mutations, [])

    def test_waits_for_the_owner_verification_and_retries(self):
        self.seed()
        chrome = FakeChrome(verify_on={"delete_preset", "forwarding"})
        env = self.env(chrome=chrome)
        code, out = self.apply(env)
        self.assertEqual(code, 0, out)
        self.assertIn("OWNER: Squarespace needs you", out)
        self.assertTrue(env.notices)
        self.assertNotIn("Squarespace Defaults", chrome.presets)
        self.assertEqual(len(chrome.rules), 1)

    def test_unanswered_verification_stops_for_the_owner_and_keeps_the_window(self):
        self.seed()
        chrome = FakeChrome(verify_on={"delete_preset"})
        chrome.needs_verify = lambda action: chrome.__dict__.update(verify_active=True, verify_snaps=10**6) or True
        code, out = self.apply(self.env(chrome=chrome), "--owner-wait", "20")
        self.assertEqual(code, domains.EXIT_OWNER)
        self.assertIn("click CONTINUE", out)
        self.assertEqual(len(chrome.windows), 2, "the owner needs the window that shows the prompt")

    def test_locked_screen_stops_before_opening_a_window(self):
        self.seed()
        chrome = FakeChrome(locked=True)
        code, out = self.apply(self.env(chrome=chrome))
        self.assertEqual(code, domains.EXIT_OWNER)
        self.assertIn("Unlock the Mac", out)
        self.assertEqual(list(chrome.windows), [1])

    def test_another_agent_on_the_desktop_means_wait(self):
        self.seed()
        chrome = FakeChrome()
        code, out = self.apply(self.env(chrome=chrome, sessions=[{"session": "other-agent", "state": "active", "idle_seconds": 12}]))
        self.assertEqual(code, domains.EXIT_NEXT)
        self.assertIn("other-agent", out)
        self.assertEqual(list(chrome.windows), [1])

    def test_conflicting_record_is_left_for_the_owner(self):
        self.seed()
        chrome = FakeChrome(presets=(), records=[{"type": "CNAME", "name": "www", "value": "old-host.example"}])
        code, out = self.apply(self.env(chrome=chrome))
        self.assertEqual(code, domains.EXIT_OWNER)
        self.assertIn("old-host.example", out)
        self.assertEqual(chrome.mutations, [])

    def test_needs_railway_records_first(self):
        code, out = self.apply(self.env(chrome=FakeChrome()))
        self.assertEqual(code, domains.EXIT_NEXT)
        self.assertIn("status --domain", out)


if __name__ == "__main__":
    unittest.main()
