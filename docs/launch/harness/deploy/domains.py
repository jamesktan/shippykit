#!/usr/bin/env python3
"""Connect an app website's custom domain: Railway hosting, Squarespace DNS.
Python 3.9+, standard library only. Uses the railway, dig, curl and cua-driver commands.

Run `status` first and again after every step. It changes nothing and ends with one NEXT line:

    python3 deploy/domains.py status --domain example.com

Other commands. Each is safe to repeat:

    projects     list Railway workspaces, projects, services and IDs
    railway      add www.<domain> to the Railway service and save the DNS records it needs
    squarespace  apply those records and the bare-domain redirect in the owner's signed-in Chrome

Exit codes: 0 done, 2 another step or a wait is needed, 3 the owner must act, 1 error.
State (no secrets) is kept in release-output/domains/<domain>.json.
"""
import argparse
import datetime
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

DOMAIN_RE = re.compile(r"^(?=.{4,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$")
IPV4_RE = re.compile(r"^\d{1,3}(?:\.\d{1,3}){3}$")
TTL_RE = re.compile(r"^\d+\s*(?:secs?|seconds?|mins?|minutes?|hrs?|hours?|days?)$", re.I)
PRIORITY_RE = re.compile(r"^(?:N/A|—|-|\d+)$")
RECORD_TYPES = {"A", "AAAA", "CNAME", "TXT", "MX", "NS", "SRV", "CAA", "HTTPS", "ALIAS"}
ROW_RE = re.compile(r"^\s*- \[(\d+)\] (.*)$")
TEXT_RE = re.compile(r'AXStaticText = "((?:[^"\\]|\\.)*)"')
PUBLIC_RESOLVERS = ("1.1.1.1", "8.8.8.8")
SQUARESPACE = "https://account.squarespace.com/domains/managed/"
REDIRECT_PROBE = "/shippykit-redirect-check"
FORWARDING_GRACE_HOURS = 48
BUSY_SECONDS = 180
LOCKED = "The Mac's screen is locked or the screen saver is on, and macOS hides windows from automation until it is unlocked. Unlock the Mac, then rerun this command."
EXIT_DONE, EXIT_ERROR, EXIT_NEXT, EXIT_OWNER = 0, 1, 2, 3


class Env:
    """Process, clock and notification access; tests replace it."""

    def run(self, cmd, timeout=60):
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
            return r.returncode, r.stdout, r.stderr
        except FileNotFoundError:
            return 127, "", f"{cmd[0]}: command not found"
        except subprocess.TimeoutExpired:
            return 124, "", f"{cmd[0]}: timed out after {timeout}s"

    def which(self, name):
        found = shutil.which(name)
        if not found and name == "cua-driver":
            local = Path.home() / ".local/bin/cua-driver"
            found = str(local) if os.access(local, os.X_OK) else None
        return found

    def sleep(self, seconds):
        time.sleep(seconds)

    def now(self):
        return time.time()

    def notify(self, message):
        if sys.platform == "darwin":
            self.run(["osascript", "-e", f"display notification {json.dumps(message)} with title \"ShippyKit\""], 10)


class OwnerAction(Exception):
    """The owner must do something only they can do (sign in, verify, edit by hand)."""


class DriverError(Exception):
    """The desktop driver or the page did not behave as expected."""


def iso(env):
    return datetime.datetime.fromtimestamp(env.now(), datetime.timezone.utc).isoformat(timespec="seconds")


def check_domain(raw):
    domain = (raw or "").strip().lower().rstrip(".")
    if domain.startswith("www."):
        raise SystemExit("Pass the bare domain (example.com), not www.example.com.")
    if not DOMAIN_RE.match(domain):
        raise SystemExit(f"Not a domain name: {raw!r}")
    return domain


def state_path(project, domain):
    return Path(project) / "release-output" / "domains" / f"{domain}.json"


def load_state(project, domain):
    path = state_path(project, domain)
    if path.is_file():
        return json.loads(path.read_text())
    return {"schema": 1, "domain": domain, "host": "www." + domain, "railway": {}, "records": [], "events": []}


def save_state(project, state, env):
    path = state_path(project, state["domain"])
    path.parent.mkdir(parents=True, exist_ok=True)
    state["updated_at"] = iso(env)
    state["events"] = state.get("events", [])[-100:]
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2) + "\n")
    tmp.replace(path)


def event(state, env, name, **detail):
    state.setdefault("events", []).append({"at": iso(env), "event": name, **detail})


def merge_railway(state, args):
    rw = dict(state.get("railway") or {})
    for key in ("project", "service", "environment", "port"):
        value = getattr(args, key, None)
        if value:
            rw[key] = value
    rw.setdefault("environment", "production")
    rw.setdefault("port", 8080)
    state["railway"] = rw
    return rw


# ---------------------------------------------------------------- Railway


def railway_json(env, args, timeout=60):
    code, out, err = env.run(["railway", *args, "--json"], timeout)
    if code != 0:
        return None, ((err or out).strip().splitlines() or [f"railway exit {code}"])[-1][:300]
    try:
        return json.loads(out), None
    except ValueError:
        return None, "railway printed something other than JSON"


def scope(rw):
    return ["--service", str(rw["service"]), "--project", str(rw["project"]), "--environment", str(rw["environment"])]


def railway_login(env):
    data, err = railway_json(env, ["whoami"], 30)
    return (data.get("name") or data.get("email") or "signed in", None) if data else (None, err)


DATABASE_SERVICE_RE = re.compile(r"(?i)^(postgres(ql)?|mysql|mariadb|redis|mongo(db)?|valkey)(\b|[-_ ])")


def railway_projects(env):
    data, err = railway_json(env, ["list"])
    if data is None:
        return None, err
    projects = []
    for p in data:
        services = [e["node"]["name"] for e in (p.get("services") or {}).get("edges", [])]
        projects.append({
            "workspace": (p.get("workspace") or {}).get("name") or "?", "id": p.get("id"), "name": p.get("name") or "",
            "services": services, "web": [s for s in services if not DATABASE_SERVICE_RE.match(s)],
            "environments": [e["node"]["name"] for e in (p.get("environments") or {}).get("edges", [])],
        })
    return projects, None


def suggest_service(env, domain):
    """The project named after the domain and its only non-database service, when unambiguous."""
    projects, _ = railway_projects(env)
    word = re.sub(r"[^a-z0-9]", "", domain.split(".")[0])
    simple = lambda name: re.sub(r"[^a-z0-9]", "", re.sub(r"(?i)[-_ ]?(website|site|web)$", "", name.lower()))
    matches = [p for p in projects or [] if word and (word in simple(p["name"]) or (simple(p["name"]) and simple(p["name"]) in word))]
    if len(matches) == 1 and len(matches[0]["web"]) == 1:
        return {"project": matches[0]["id"], "service": matches[0]["web"][0], "name": matches[0]["name"]}
    return None


def railway_domains(env, rw):
    data, err = railway_json(env, ["domain", "list", *scope(rw)])
    if data is None:
        return None, err
    return [d.get("domain", "").lower() for d in data.get("domains", [])], None


def railway_domain(env, host, rw):
    data, err = railway_json(env, ["domain", "status", host, *scope(rw)])
    if data is None:
        return None, err
    d = data.get("domain") or {}
    target = next((r.get("requiredValue") for r in d.get("dnsRecords") or [] if str(r.get("recordType", "")).endswith("CNAME")), "")
    verification = d.get("verification") or {}
    return {
        "id": d.get("id"),
        "target": (target or "").rstrip(".").lower(),
        "verified": bool(verification.get("verified")),
        "txt_host": verification.get("dnsHost"),
        "txt_value": verification.get("token"),
        "certificate": (d.get("certificate") or {}).get("status") or "unknown",
    }, None


def required_records(info):
    records = [{"type": "CNAME", "name": "www", "value": info["target"]}]
    if info.get("txt_host") and info.get("txt_value"):
        records.append({"type": "TXT", "name": info["txt_host"], "value": info["txt_value"]})
    return records


# ---------------------------------------------------------------- DNS and HTTP


def dig(env, name, rtype, server=None):
    cmd = ["dig", "+short", "+time=3", "+tries=2", name, rtype] + (["@" + server] if server else [])
    code, out, _ = env.run(cmd, 20)
    if code != 0:
        return None
    values = []
    for line in out.splitlines():
        line = line.strip()
        if not line or line.startswith(";"):
            continue
        if rtype == "TXT":
            line = "".join(re.findall(r'"((?:[^"\\]|\\.)*)"', line)) or line
        elif rtype in ("CNAME", "NS"):
            line = line.rstrip(".").lower()
        values.append(line)
    return values


def http(env, url, resolve=None, timeout=20):
    cmd = ["curl", "-sS", "-o", "/dev/null", "-m", str(timeout), "-w", "%{http_code} %{redirect_url}", url]
    if resolve:
        cmd[1:1] = ["--resolve", resolve]
    code, out, err = env.run(cmd, timeout + 5)
    if code != 0:
        return None, "", (err.strip() or f"curl exit {code}")[:200]
    status, _, location = out.strip().partition(" ")
    return int(status or 0), location.strip(), None


def page_origin(env, url, resolve):
    """The canonical or og:url origin a page declares, or None."""
    code, out, _ = env.run(["curl", "-sS", "-m", "20", "--max-filesize", "2000000", "--resolve", resolve, url], 25)
    if code != 0:
        return None
    for tag in re.finditer(r"<(?:link|meta)\b[^>]*>", out, re.I):
        attrs = {k.lower(): v for k, v in re.findall(r'([\w:-]+)\s*=\s*["\']([^"\']*)["\']', tag.group(0))}
        if attrs.get("rel", "").lower() == "canonical" and attrs.get("href"):
            return attrs["href"]
        if attrs.get("property", "").lower() == "og:url" and attrs.get("content"):
            return attrs["content"]
    return None


# ---------------------------------------------------------------- status


def diagnose(env, domain, state, paths):
    host = "www." + domain
    rw = state.get("railway") or {}
    checks, ctx = [], {"domain": domain, "host": host, "rw": rw}

    def add(key, st, detail):
        checks.append({"check": key, "state": st, "detail": detail})
        return st

    missing = [t for t in ("railway", "dig", "curl") if not env.which(t)]
    if missing:
        add("tools", "owner", "missing: " + ", ".join(missing))
        return checks, decide(checks, ctx, state, env)
    who, err = railway_login(env)
    if add("railway_login", "ok" if who else "owner", who or err) != "ok":
        return checks, decide(checks, ctx, state, env)
    if add("railway_service", "ok" if rw.get("project") and rw.get("service") else "missing",
           f"{rw.get('service')} in project {rw.get('project')} ({rw.get('environment')})" if rw.get("project") else "not recorded yet") != "ok":
        ctx["suggest"] = suggest_service(env, domain)
        return checks, decide(checks, ctx, state, env)
    names, err = railway_domains(env, rw)
    if names is None:
        add("railway_domain", "error", err)
        return checks, decide(checks, ctx, state, env)
    ctx["apex_on_railway"] = domain in names
    if host not in names:
        add("railway_domain", "missing", f"{host} is not on the Railway service yet")
        return checks, decide(checks, ctx, state, env)
    info, err = railway_domain(env, host, rw)
    if not info or not info["target"]:
        add("railway_domain", "error", err or "Railway returned no CNAME target")
        return checks, decide(checks, ctx, state, env)
    ctx["info"] = info
    add("railway_domain", "ok", f"{host} → {info['target']}, ownership {'verified' if info['verified'] else 'not verified yet'}")
    cert = info["certificate"]
    add("certificate", "ok" if cert.endswith("VALID") else ("error" if "FAIL" in cert else "pending"), cert)

    ns = dig(env, domain, "NS", PUBLIC_RESOLVERS[0]) or []
    ctx["ns"] = ns
    if not ns:
        add("nameservers", "pending", "the registry does not publish this domain yet")
        return checks, decide(checks, ctx, state, env)
    on_squarespace = any(n.endswith("squarespacedns.com") for n in ns)
    ctx["squarespace"] = on_squarespace
    add("nameservers", "ok" if on_squarespace else "other", ", ".join(sorted(ns)))

    cname = dig(env, host, "CNAME", ns[0]) or []
    add("dns_cname", "ok" if info["target"] in cname else "missing",
        f"{host} CNAME at {ns[0]}: {', '.join(cname) or 'none'} (needs {info['target']})")
    if info["verified"]:
        add("dns_txt", "ok", "not needed: Railway already verified ownership")
    else:
        txt = dig(env, f"{info['txt_host']}.{domain}", "TXT", ns[0]) or []
        add("dns_txt", "ok" if info["txt_value"] in txt else "missing", f"{info['txt_host']} TXT at {ns[0]}: {'present' if info['txt_value'] in txt else 'absent'}")
    public = [dig(env, host, "CNAME", r) or [] for r in PUBLIC_RESOLVERS]
    add("dns_public", "ok" if all(info["target"] in p for p in public) else "pending",
        "; ".join(f"{r}: {', '.join(p) or 'none'}" for r, p in zip(PUBLIC_RESOLVERS, public)))

    ips = [v for v in dig(env, info["target"], "A", PUBLIC_RESOLVERS[0]) or [] if IPV4_RE.match(v)]
    if ips:
        resolve = f"{host}:443:{ips[0]}"
        results = [(p, *http(env, f"https://{host}{p}", resolve)[::2]) for p in paths]
        bad = [f"{p} → {c or e}" for p, c, e in results if not c or not 200 <= c < 300]
        add("https", "error" if bad else "ok", ("; ".join(bad) if bad else "all answer 200: " + ", ".join(paths)))
        origin = page_origin(env, f"https://{host}/", resolve)
        if origin is None:
            add("canonical", "unknown", "the home page declares no canonical or og:url address")
        else:
            add("canonical", "ok" if origin.rstrip("/").startswith(f"https://{host}") else "wrong", origin)
    else:
        add("https", "error", f"could not resolve {info['target']}")

    status, location, err = http(env, f"http://{domain}{REDIRECT_PROBE}")
    want = f"https://{host}{REDIRECT_PROBE}"
    if status in (301, 308) and location == want:
        add("redirect", "ok", f"{domain} → {want} ({status})")
    elif status in (301, 302, 307, 308) and location.startswith(f"https://{host}"):
        why = "temporary redirect" if status in (302, 307) else "drops the path"
        add("redirect", "wrong", f"{domain} answers {status} → {location} ({why})")
    else:
        add("redirect", "missing", f"{domain} answers {status or err} {location}".strip())
    return checks, decide(checks, ctx, state, env)


def recent_forwarding(state, env):
    for e in reversed(state.get("events", [])):
        if e.get("event") == "forwarding_created":
            at = datetime.datetime.fromisoformat(e["at"]).timestamp()
            return env.now() - at < FORWARDING_GRACE_HOURS * 3600
    return False


def decide(checks, ctx, state, env):
    s = {c["check"]: c["state"] for c in checks}
    d, rw = ctx["domain"], ctx["rw"]
    run = f"python3 deploy/domains.py {{}} --domain {d}"

    def out(actor, message, command=None, wait=None):
        return {"actor": actor, "message": message, "command": command, "wait_minutes": wait}

    if s.get("tools") == "owner":
        return out("owner", "Install the missing command-line tools listed above (Railway CLI: https://docs.railway.com/guides/cli), then rerun status.")
    if s.get("railway_login") == "owner":
        return out("owner", "Sign in to Railway: run `railway login` in a terminal (it opens a browser), then rerun status.")
    if s.get("railway_service") == "missing":
        hint = ctx.get("suggest")
        if hint:
            return out("agent", f"Railway project {hint['name']!r} matches this domain and has one web service, {hint['service']!r}. Connect the domain to it.",
                       f"{run.format('railway')} --project {hint['project']} --service {hint['service']}")
        return out("agent", "No Railway project clearly matches this domain. Run `python3 deploy/domains.py projects`, pick the app's website project and its web service (marked `web:`), then run the railway step with them. If none is clearly the website, ask the owner.",
                   f"{run.format('railway')} --project <project-id> --service <service-name>")
    if s.get("railway_domain") == "missing":
        return out("agent", f"Add www.{d} to the Railway service.", run.format("railway"))
    if s.get("railway_domain") == "error":
        return out("agent", "Railway could not be read with the saved project/service. Check them with `python3 deploy/domains.py projects`, then rerun the railway step with the right --project and --service.")
    if s.get("nameservers") == "pending":
        return out("wait", "The domain is not published by its registry yet (normal for a few minutes after purchase). Rerun status in 5 minutes.", wait=5)
    records = required_records(ctx["info"])
    if s.get("nameservers") == "other":
        listing = "; ".join(f"{r['type']} {r['name']} → {r['value']}" for r in records)
        return out("owner", f"DNS for {d} is hosted at {', '.join(ctx['ns'])}, not Squarespace, so this helper cannot edit it. Add these records there: {listing}. Point {d} at www.{d} with a 301 redirect. Then rerun status.")
    if s.get("dns_cname") == "missing" or s.get("dns_txt") == "missing" or (s.get("redirect") == "missing" and not recent_forwarding(state, env)):
        return out("agent", "Apply the Railway records and the bare-domain redirect in Squarespace.", run.format("squarespace"))
    if s.get("dns_public") == "pending":
        return out("wait", "Squarespace has the records; public DNS has not caught up yet. Rerun status in 10 minutes.", wait=10)
    if s.get("certificate") == "error":
        return out("agent", "Railway's certificate failed. Ask Railway to retry, then rerun status in 10 minutes.",
                   f"railway domain certificate retry www.{d} {' '.join(scope(rw))}")
    if s.get("certificate") == "pending":
        return out("wait", "DNS is correct; Railway is still issuing the certificate. Rerun status in 10 minutes.", wait=10)
    if s.get("https") == "error":
        return out("agent", "The website does not answer correctly on Railway. Check the latest deploy and its logs, fix the site, then rerun status.",
                   f"railway deployment list {' '.join(scope(rw))} --json")
    if s.get("redirect") == "wrong":
        return out("owner", f"The redirect from {d} is set up but not as a permanent redirect that keeps paths. In Squarespace (https://account.squarespace.com/domains/managed/{d}/website) edit the rule: Permanent Redirect (301), Maintain paths. Then rerun status.")
    if s.get("canonical") == "wrong":
        return out("agent", f"The site still declares its old address as canonical. Set its public origin to https://www.{d} and redeploy, then rerun status.",
                   f"railway variable set PUBLIC_ORIGIN=https://www.{d} {' '.join(scope(rw))}")
    if s.get("redirect") == "missing":
        return out("wait", f"https://www.{d} is live. Squarespace says the {d} redirect can take up to 48 hours to start; rerun status later.", wait=60)
    note = " Railway still lists the bare domain too; remove it with `railway domain delete " + d + "` if it is unused." if ctx.get("apex_on_railway") else ""
    return out("done", f"https://www.{d} is live and {d} redirects to it. If this run is allowed to edit the store listing, point its marketing, support and privacy URLs at https://www.{d}.{note}")


def print_status(domain, checks, nxt, as_json):
    if as_json:
        print(json.dumps({"domain": domain, "checks": checks, "next": nxt}, indent=2))
        return
    print(f"{domain} → https://www.{domain}")
    for c in checks:
        print(f"  {c['state']:<8} {c['check']}: {c['detail']}")
    print(f"NEXT [{nxt['actor']}]: {nxt['message']}")
    if nxt.get("command"):
        print(f"  $ {nxt['command']}")


def cmd_status(args, env):
    domain = check_domain(args.domain)
    state = load_state(args.root, domain)
    rw = merge_railway(state, args)
    checks, nxt = diagnose(env, domain, state, [p if p.startswith("/") else "/" + p for p in args.paths.split(",")])
    if args.project or args.service or args.environment or args.port:
        save_state(args.root, state, env)
    print_status(domain, checks, nxt, args.json)
    return {"done": EXIT_DONE, "owner": EXIT_OWNER}.get(nxt["actor"], EXIT_NEXT)


# ---------------------------------------------------------------- projects and railway


def cmd_projects(args, env):
    projects, err = railway_projects(env)
    if projects is None:
        print(f"Could not list Railway projects: {err}. If you are signed out, run `railway login`.")
        return EXIT_OWNER
    for p in sorted(projects, key=lambda p: (p["workspace"], p["name"])):
        print(f"{p['workspace']} | {p['name']} | project {p['id']} | web: {', '.join(p['web']) or '-'} | all services: {', '.join(p['services']) or '-'} | environments: {', '.join(p['environments']) or '-'}")
    print("Use the app's website project and its `web:` service with the railway step.")
    return EXIT_DONE


def cmd_railway(args, env):
    domain = check_domain(args.domain)
    state = load_state(args.root, domain)
    rw = merge_railway(state, args)
    if not (rw.get("project") and rw.get("service")):
        print("Pass --project <project-id> --service <service-name>. `python3 deploy/domains.py projects` lists them.")
        return EXIT_ERROR
    if not railway_login(env)[0]:
        print("Railway is signed out. The owner must run `railway login`, then rerun this command.")
        return EXIT_OWNER
    host = state["host"]
    names, err = railway_domains(env, rw)
    if names is None:
        print(f"Could not read the service's domains: {err}")
        return EXIT_ERROR
    if host not in names:
        data, err = railway_json(env, ["domain", host, "--port", str(rw["port"]), *scope(rw)])
        if data is None:
            print(f"Railway refused to add {host}: {err}")
            return EXIT_ERROR
        event(state, env, "railway_domain_added", host=host)
    info = None
    for _ in range(5):
        info, err = railway_domain(env, host, rw)
        if info and info["target"]:
            break
        env.sleep(3)
    if not info or not info["target"]:
        print(f"Railway did not return the DNS target for {host}: {err}")
        return EXIT_ERROR
    rw["domain_id"] = info["id"]
    state["records"] = required_records(info)
    event(state, env, "railway_records_saved", target=info["target"], verified=info["verified"])
    save_state(args.root, state, env)
    print(f"{host} is on Railway service {rw['service']}. DNS records it needs:")
    for r in state["records"]:
        print(f"  {r['type']:<6} {r['name']:<24} {r['value']}")
    if domain in names:
        print(f"Note: Railway also lists the bare domain {domain}. It cannot verify there with Squarespace; remove it if unused: railway domain delete {domain} --yes {' '.join(scope(rw))}")
    print(f"NEXT: python3 deploy/domains.py status --domain {domain}")
    return EXIT_DONE


# ---------------------------------------------------------------- Squarespace page model


def rows(tree):
    for line in (tree or "").splitlines():
        m = ROW_RE.match(line)
        if m:
            yield m.group(1), m.group(2)


def texts(tree, after=None):
    started = after is None
    values = []
    for _, text in rows(tree):
        if not started:
            started = after in text
            continue
        if "AXPopUpButton \"Tab search\"" in text:
            break
        m = TEXT_RE.search(text)
        if m:
            values.append((m.group(1).replace('\\"', '"'), "actions=[press]" in text))
    return values


def presets(tree):
    return re.findall(r'AXButton "Delete preset ([^"]+)"', tree or "")


def custom_records(tree):
    values = [v for v, pressable in texts(tree, 'AXHeading "Custom records"') if not pressable]
    found = []
    for i in range(len(values) - 4):
        kind, name, priority, ttl, data = values[i:i + 5]
        if kind in RECORD_TYPES and PRIORITY_RE.match(priority) and TTL_RE.match(ttl):
            record = {"type": kind, "name": name, "value": data}
            if record not in found:
                found.append(record)
    return found


def same_record(a, b):
    def norm(r):
        value = r["value"].strip()
        if r["type"] != "TXT":
            value = value.rstrip(".").lower()
        return r["type"].upper(), r["name"].strip().lower(), value
    return norm(a) == norm(b)


def conflicts(existing, wanted):
    clashes = []
    for want in wanted:
        for have in existing:
            if have["name"].lower() != want["name"].lower() or same_record(have, want):
                continue
            if want["type"] == "CNAME" and have["type"] in ("CNAME", "A", "AAAA"):
                clashes.append(have)
    return clashes


def forwarding_rules(tree):
    values = [v for v, _ in texts(tree, 'AXHeading "Domain forwarding"')]
    rules = []
    for i, v in enumerate(values[:-1]):
        if v == "TO":
            rule = {"to": values[i + 1]}
            for label, key in (("REDIRECT TYPE", "type"), ("PATH FORWARDING", "paths")):
                j = next((k for k in range(i + 2, min(i + 8, len(values) - 1)) if values[k] == label), None)
                rule[key] = values[j + 1] if j is not None else ""
            rules.append(rule)
    return rules


def rule_state(rules, domain):
    want = f"https://www.{domain}"
    mine = [r for r in rules if r["to"].rstrip("/").lower() == want]
    if not mine:
        return "missing"
    good = any(r["type"].lower().startswith("permanent") and re.search(r"(?i)forward|maintain", r["paths"]) for r in mine)
    return "ok" if good else "wrong"


def verify_prompt(tree):
    return "Verify to continue" in (tree or "")


def signed_out(snapshot):
    title = snapshot.get("window_title") or ""
    return "Squarespace Domains" not in title and bool(re.search(r"(?i)log ?in|sign ?in", title))


# ---------------------------------------------------------------- Squarespace driver


class Squarespace:
    """Drives one Chrome window of the owner's signed-in browser. Every action is read back."""

    def __init__(self, env, cua, domain, owner_wait):
        self.env, self.cua, self.domain, self.owner_wait = env, cua, domain, owner_wait
        self.session = f"shippykit-dns-{int(env.now())}"
        self.pid = self.win = None

    def call(self, tool, args):
        a = dict(args)
        a.setdefault("session", self.session)
        code, out, err = self.env.run([self.cua, "call", tool, json.dumps(a)], 90)
        try:
            data = json.loads(out)
        except ValueError:
            raise DriverError(f"cua-driver {tool}: {(out + err).strip()[:300]}") from None
        if isinstance(data, dict) and data.get("effect") == "refused":
            raise DriverError(f"cua-driver {tool} refused: {str(data.get('reason'))[:300]}")
        return data

    def chrome_windows(self):
        found = self.call("list_windows", {"app": "Google Chrome"}).get("windows", [])
        return [w for w in found if w.get("is_on_screen")]

    def open_window(self, url):
        """A window of our own; other agents' and the owner's windows are never touched."""
        before = {w["window_id"] for w in self.call("list_windows", {"app": "Google Chrome"}).get("windows", [])}
        if sys.platform == "darwin":
            # Opens in the background: the owner's frontmost app keeps focus.
            code, _, err = self.env.run(["open", "-g", "-na", "Google Chrome", "--args", "--new-window", url], 30)
            if code != 0:
                raise OwnerAction(f"Google Chrome could not be opened ({err.strip()[:120]}). Install Chrome and sign in to Squarespace, then rerun.")
        else:
            anchors = [w for w in self.chrome_windows() if w.get("title")]
            if not anchors:
                raise OwnerAction("Open Google Chrome, sign in to Squarespace at https://account.squarespace.com, then rerun this command.")
            self.call("invoke_menu", {"pid": anchors[0]["pid"], "window_id": anchors[0]["window_id"], "path": ["File", "New Window"]})
        for _ in range(40):
            self.env.sleep(0.5)
            new = [w for w in self.chrome_windows() if w["window_id"] not in before]
            if new:
                self.pid, self.win = new[0]["pid"], new[0]["window_id"]
                return
        raise DriverError("Chrome did not open a new window")

    def snap(self, pid=None, win=None, limit=1500):
        s = self.call("get_window_state", {"pid": pid or self.pid, "window_id": win or self.win, "include_screenshot": False, "max_elements": limit})
        if str(s.get("degraded_reason", "")).startswith("screen_locked"):
            raise OwnerAction(LOCKED)
        if "tree_markdown" not in s:
            raise DriverError(f"could not read the Chrome window: {str(s)[:200]}")
        return s

    def check_unlocked(self):
        """macOS hides every window from automation while the screen is locked."""
        for w in self.chrome_windows()[:1]:
            self.snap(w["pid"], w["window_id"], 5)

    def token(self, snapshot, pattern, last=False):
        hits = [row for row, text in rows(snapshot["tree_markdown"]) if re.search(pattern, text)]
        if not hits:
            raise DriverError(f"Squarespace page has no element matching {pattern!r}; the dashboard may have changed")
        return f"{snapshot['snapshot_id']}:{hits[-1 if last else 0]}"

    def click(self, pattern):
        self.call("click", {"element_token": self.token(self.snap(), pattern)})

    def fill(self, pattern, value):
        self.call("set_value", {"element_token": self.token(self.snap(), pattern), "value": value})

    def wait(self, ready, seconds=20):
        end = self.env.now() + seconds
        while True:
            s = self.snap()
            if verify_prompt(s["tree_markdown"]) or ready(s):
                return s
            if self.env.now() >= end:
                return s
            self.env.sleep(1.5)

    def goto(self, url, marker):
        self.fill(r'AXTextField "Address and search bar"', url)
        self.call("press_key", {"element_token": self.token(self.snap(), r'AXTextField "Address and search bar"'), "key": "return"})
        s = self.wait(lambda s: marker in s["tree_markdown"] or signed_out(s), 40)
        if signed_out(s):
            raise OwnerAction(f"Squarespace is signed out. Sign in at https://account.squarespace.com in Chrome (window titled {s.get('window_title')!r}), then rerun this command.")
        if verify_prompt(s["tree_markdown"]):
            self.owner_verify(s)
            return self.goto(url, marker)
        if marker not in s["tree_markdown"]:
            raise DriverError(f"{url} did not finish loading (window title {s.get('window_title')!r})")
        return s

    def owner_verify(self, snapshot):
        """Squarespace asks the owner to confirm their identity before some changes."""
        title = snapshot.get("window_title")
        message = f"Squarespace needs you: in the Chrome window {title!r}, click CONTINUE on 'Verify to continue' and finish signing in."
        print("OWNER: " + message, flush=True)
        self.env.notify(message)
        end = self.env.now() + self.owner_wait
        while self.env.now() < end:
            self.env.sleep(5)
            if not verify_prompt(self.snap()["tree_markdown"]):
                return
        raise OwnerAction(message + " Then rerun this command.")

    def act(self, ready, seconds=20):
        s = self.wait(ready, seconds)
        if verify_prompt(s["tree_markdown"]):
            self.owner_verify(s)
            return None
        return s

    def delete_preset(self, name):
        self.click(re.escape(f'AXButton "Delete preset {name}"'))
        self.act(lambda s: name not in presets(s["tree_markdown"]), 20)

    def add_record(self, record):
        self.click(r'AXButton "ADD RECORD"')
        if not self.act(lambda s: 'AXComboBox "TYPE"' in s["tree_markdown"], 15):
            return
        self.click(r'AXComboBox "TYPE"')
        option = re.escape(f'AXStaticText = "{record["type"]}" [actions=[press]]')
        self.wait(lambda s: re.search(option, s["tree_markdown"]), 10)
        self.click(option)
        self.wait(lambda s: f'AXComboBox "TYPE" = "{record["type"]}"' in s["tree_markdown"], 10)
        self.fill(r'AXTextField "NAME"', record["name"])
        s = self.snap()
        value_field = r'AXTextField "TEXT"' if 'AXTextField "TEXT"' in s["tree_markdown"] else r'AXTextField "DATA"'
        self.fill(value_field, record["value"])
        s = self.snap()
        shown = s["tree_markdown"]
        if f'AXTextField "NAME" = "{record["name"]}"' not in shown or f'= "{record["value"]}"' not in shown:
            raise DriverError(f"the add-record form did not keep {record['type']} {record['name']}")
        self.click(r'AXButton "save record"')
        s = self.act(lambda s: any(same_record(r, record) for r in custom_records(s["tree_markdown"])), 20)
        if s is not None and not any(same_record(r, record) for r in custom_records(s["tree_markdown"])):
            raise DriverError(f"Squarespace did not show {record['type']} {record['name']} after saving")

    def add_forwarding(self):
        self.click(r'AXButton "Add domain forwarding url"')
        if not self.act(lambda s: 'AXTextField "SUBDOMAIN"' in s["tree_markdown"], 15):
            return False
        self.fill(r'AXTextField "SUBDOMAIN"', "@")
        self.fill(r'AXTextField "ENTER WEBSITE URL"', f"https://www.{self.domain}")
        self.click(r'AXButton "Advanced settings"')
        self.wait(lambda s: "Permanent Redirect (301)" in s["tree_markdown"], 10)
        self.click(re.escape('AXRadioButton "Permanent Redirect (301)"'))
        self.click(re.escape('AXRadioButton "Maintain paths"'))
        self.click(r'AXButton "SAVE"')
        s = self.act(lambda s: "Domain forwarding rule has been created" in s["tree_markdown"], 25)
        if s is None:
            return False
        if "Domain forwarding rule has been created" not in s["tree_markdown"]:
            raise DriverError("Squarespace did not confirm the forwarding rule")
        self.click(r'AXButton "OKAY"')
        return True

    def close(self):
        try:
            if self.win is not None:
                s = self.snap()
                tab_close = None
                seen_tabs = False
                for row, text in rows(s["tree_markdown"]):
                    seen_tabs = seen_tabs or 'AXPopUpButton "Tab search"' in text
                    if seen_tabs and 'AXButton "Close" [actions=[press]]' in text:
                        tab_close = f"{s['snapshot_id']}:{row}"
                        break
                if tab_close:
                    self.call("click", {"element_token": tab_close})
        except DriverError:
            pass
        finally:
            try:
                self.call("end_session", {})
            except DriverError:
                pass


def other_sessions(env, cua):
    code, out, _ = env.run([cua, "sessions", "--json"], 20)
    try:
        sessions = json.loads(out).get("sessions", []) if code == 0 else []
    except ValueError:
        sessions = []
    return [s.get("session", "?") for s in sessions if s.get("state") == "active" and s.get("idle_seconds", BUSY_SECONDS) < BUSY_SECONDS]


def cmd_squarespace(args, env):
    domain = check_domain(args.domain)
    state = load_state(args.root, domain)
    records = state.get("records") or []
    if not records:
        print(f"No Railway records saved for {domain} yet. Run: python3 deploy/domains.py status --domain {domain}")
        return EXIT_NEXT
    cua = env.which("cua-driver")
    if not cua:
        print("Cua Driver is not installed. Follow deploy/CUA-DRIVER.md (the owner approves the install), then rerun.")
        return EXIT_OWNER
    busy = other_sessions(env, cua)
    if busy:
        print(f"Another agent is using the desktop ({', '.join(busy)}). Rerun this command in 3 minutes.")
        return EXIT_NEXT
    sq = Squarespace(env, cua, domain, args.owner_wait)
    dns_url, site_url = f"{SQUARESPACE}{domain}/dns/dns-settings", f"{SQUARESPACE}{domain}/website"
    changed, keep_window = [], False
    try:
        sq.check_unlocked()
        sq.open_window(dns_url)
        for _ in range(8):
            s = sq.goto(dns_url, 'AXHeading "Custom records"')
            tree = s["tree_markdown"]
            existing = custom_records(tree)
            clashes = conflicts(existing, records)
            if clashes:
                listing = "; ".join(f"{c['type']} {c['name']} → {c['value']}" for c in clashes)
                raise OwnerAction(f"Squarespace already has records that conflict with Railway's: {listing}. Decide whether to delete them at {dns_url}, then rerun.")
            todo = (["delete preset Squarespace Defaults"] if "Squarespace Defaults" in presets(tree) else [])
            todo += [f"add {r['type']} {r['name']} → {r['value']}" for r in records if not any(same_record(e, r) for e in existing)]
            s = sq.goto(site_url, 'AXHeading "Domain forwarding"')
            forwarding = rule_state(forwarding_rules(s["tree_markdown"]), domain)
            if forwarding == "wrong":
                raise OwnerAction(f"A redirect to https://www.{domain} exists but is not Permanent (301) with Maintain paths. Edit it at {site_url}, then rerun.")
            if forwarding == "missing":
                todo.append(f"add redirect {domain} → https://www.{domain} (301, keep paths)")
            if not todo:
                break
            if args.dry_run:
                print("Would change:\n  " + "\n  ".join(todo))
                return EXIT_NEXT
            step = todo[0]
            print(f"Applying: {step}", flush=True)
            if step.startswith("delete preset"):
                sq.goto(dns_url, 'AXHeading "Custom records"')
                sq.delete_preset("Squarespace Defaults")
            elif step.startswith("add redirect"):
                if sq.add_forwarding():
                    event(state, env, "forwarding_created", to=f"https://www.{domain}")
            else:
                sq.goto(dns_url, 'AXHeading "Custom records"')
                sq.add_record(next(r for r in records if not any(same_record(e, r) for e in existing)))
            changed.append(step)
            event(state, env, "squarespace_step", step=step)
        else:
            raise DriverError("Squarespace did not reach the expected state after 8 rounds")
    except OwnerAction as e:
        keep_window = True
        print(f"OWNER ACTION: {e}")
        return EXIT_OWNER
    except DriverError as e:
        print(f"ERROR: {e}")
        return EXIT_ERROR
    finally:
        if changed:
            save_state(args.root, state, env)
        if not keep_window:
            sq.close()
        else:
            try:
                sq.call("end_session", {})
            except DriverError:
                pass
    print("Squarespace is set up: " + ("; ".join(changed) if changed else "nothing needed changing") + ".")
    print(f"NEXT: python3 deploy/domains.py status --domain {domain}")
    return EXIT_DONE


def main(argv=None, env=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=("status", "projects", "railway", "squarespace"))
    parser.add_argument("--domain", help="the bare domain, e.g. example.com")
    parser.add_argument("--root", default=".", help="app repository (default: current directory)")
    parser.add_argument("--project", help="Railway project ID (saved after the first use)")
    parser.add_argument("--service", help="Railway service name that serves the website (saved)")
    parser.add_argument("--environment", help="Railway environment (default production; saved)")
    parser.add_argument("--port", type=int, help="port the website listens on (default 8080; saved)")
    parser.add_argument("--paths", default="/,/support,/privacy", help="pages that must answer 200 (status)")
    parser.add_argument("--dry-run", action="store_true", help="squarespace: read and list changes without making them")
    parser.add_argument("--owner-wait", type=int, default=300, help="squarespace: seconds to wait for the owner's sign-in check")
    parser.add_argument("--json", action="store_true", help="status: print JSON")
    args = parser.parse_args(argv)
    env = env or Env()
    if args.command == "projects":
        return cmd_projects(args, env)
    if not args.domain:
        parser.error("--domain is required")
    return {"status": cmd_status, "railway": cmd_railway, "squarespace": cmd_squarespace}[args.command](args, env)


if __name__ == "__main__":
    sys.exit(main())
