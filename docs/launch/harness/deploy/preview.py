#!/usr/bin/env python3
"""Build and serve a public-only local release gallery. Python 3.9+, no dependencies."""

import argparse
from datetime import datetime, timezone
import hashlib
import html
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import tempfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlsplit


OWNER = "shippykit-preview-v1"
REGISTRY = ".shippykit-preview.json"
MEDIA_KINDS = {
    "app_store_screenshot", "app_store_preview", "preview_poster", "promo_image",
    "promo_video", "app_icon", "store_icon", "launcher_icon",
    "asset_revision_preview",
}
ICON_KINDS = {"app_icon", "store_icon", "launcher_icon"}
COPY_KINDS = {"store_copy", "preview_copy"}
MIME = {
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".webp": "image/webp", ".mp4": "video/mp4", ".m4v": "video/mp4",
    ".mov": "video/quicktime", ".webm": "video/webm", ".txt": "text/plain; charset=utf-8",
    ".html": "text/html; charset=utf-8",
}
PRIVATE_PARTS = {
    "captures", "raw", "rawcaptures", "raw-captures", "builds", "profiles",
    "logs", "results", "credentials", "secrets", "private", "inputs",
}
PRIVATE_DOCUMENTS = {"readme.md", "readme.txt", "state.md", "app.md", "needs-input.md"}
PUBLIC_HEADINGS = {
    "name", "title", "subtitle", "promotional text", "short description", "description",
    "keywords", "feature and benefit bullets", "release notes",
}
CSP = ("default-src 'none'; img-src 'self'; media-src 'self'; style-src 'unsafe-inline'; "
       "script-src 'unsafe-inline'; connect-src 'none'; base-uri 'none'; form-action 'none'")
GENERATED_PATH = re.compile(r"(?:index\.html|assets/[a-f0-9]{64}\.(?:png|jpg|jpeg|webp|mp4|m4v|mov|webm|txt))\Z")


def sha256(stream):
    digest = hashlib.sha256()
    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
        digest.update(chunk)
    return digest.hexdigest()


def relative_parts(value):
    if not isinstance(value, str) or not value or "\\" in value or ":" in value or "\x00" in value:
        raise ValueError("Unsafe relative path")
    parts = value.split("/")
    if PurePosixPath(value).is_absolute() or any(part in {"", ".", ".."} for part in parts):
        raise ValueError("Unsafe relative path")
    return parts


def open_regular(root, relative):
    """Reject symlinks (including parent components), directories and special files."""
    parts = relative_parts(relative)
    path = root
    if root.is_symlink() or not root.is_dir():
        raise ValueError("Expected a real directory")
    for part in parts:
        path = path / part
        if path.is_symlink():
            raise ValueError("Symlinks are not public assets")
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError("Path escapes its directory")
    if not stat.S_ISREG(path.stat().st_mode):
        raise ValueError("Expected a regular file")
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0))
    stream = os.fdopen(descriptor, "rb")
    if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
        stream.close()
        raise ValueError("Expected a regular file")
    return stream


def read_json(root, relative):
    with open_regular(root, relative) as stream:
        return json.load(stream)


def normalized_heading(value):
    return re.sub(r"\s+", " ", value.strip().rstrip("#").strip()).replace("’", "'").casefold()


def public_heading(value):
    value = normalized_heading(value)
    return value in PUBLIC_HEADINGS or bool(re.fullmatch(r"what's new(?:\s.*)?", value))


def store_sections(markdown, app_name):
    """Allow known sections; unknown sections also exclude all their descendants."""
    lines = markdown.splitlines()
    headings = []
    fence = None
    index = 0
    while index < len(lines):
        line = lines[index]
        marker = re.match(r"^\s{0,3}(`{3,}|~{3,})", line)
        if marker:
            run = marker.group(1)
            if fence is None:
                fence = run
            elif run[0] == fence[0] and len(run) >= len(fence):
                fence = None
            headings.append(("skip", None, None))
        elif fence is not None:
            headings.append(("skip", None, None))
        else:
            atx = re.match(r"^\s{0,3}(#{1,6})\s+(.+?)\s*$", line)
            setext = (index + 1 < len(lines) and line.strip() and
                      re.fullmatch(r"\s{0,3}(?:=+|-+)\s*", lines[index + 1]))
            if atx:
                headings.append(("heading", len(atx.group(1)), atx.group(2).rstrip("#").strip()))
            elif setext:
                headings.append(("heading", 1 if lines[index + 1].lstrip().startswith("=") else 2, line.strip()))
                index += 1
            else:
                headings.append(("text", None, line))
        index += 1

    app = normalized_heading(app_name)
    document_titles = {"store copy", "app store copy", "google play copy", "store listing", app}
    for separator in (" — ", " - ", ": ", " – "):
        document_titles.update(app + separator + suffix for suffix in ("store copy", "app store copy", "google play copy", "store listing"))
    stack, sections = [], []
    current = None
    first_heading = True
    for kind, level, value in headings:
        if kind == "heading":
            while stack and stack[-1][0] >= level:
                stack.pop()
            container = first_heading and level == 1 and normalized_heading(value) in document_titles
            allowed = public_heading(value) and all(entry[1] for entry in stack)
            stack.append((level, (allowed or container) and all(entry[1] for entry in stack)))
            current = None
            if allowed:
                current = [value, []]
                sections.append(current)
            first_heading = False
        elif kind == "text" and current is not None and all(entry[1] for entry in stack):
            current[1].append(value)
    return [(title, "\n".join(body).strip()) for title, body in sections if "\n".join(body).strip()]


def safe_label(value, default, limit=100):
    if not isinstance(value, (str, int)) or isinstance(value, bool):
        return default
    text = str(value)
    if not text.strip() or len(text) > limit or any(ord(char) < 32 for char in text):
        return default
    return text


def history_text(value, field, limit=800):
    """Accept explicit public summaries, never arbitrary nested manifest data."""
    if not isinstance(value, str) or safe_label(value, "", limit) != value or not value.strip():
        raise ValueError("Asset history requires a valid public " + field)
    return value


def history_id(value, field):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", value):
        raise ValueError("Asset history has an invalid " + field)
    return value


def history_date(value):
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}(?:T\d{2}:\d{2}:\d{2}Z)?", value):
        raise ValueError("Asset history dates must be YYYY-MM-DD or UTC YYYY-MM-DDTHH:MM:SSZ")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=timezone.utc)
    except ValueError as error:
        raise ValueError("Asset history contains an invalid calendar date") from error


def asset_history(manifest, media):
    """Validate references and return only the explicitly public schema fields."""
    previews = {}
    for item in media:
        if item["kind"] == "asset_revision_preview":
            if item["source_path"] in previews:
                raise ValueError("Duplicate asset revision preview manifest path")
            previews[item["source_path"]] = item
    if "asset_history" not in manifest:
        if previews:
            raise ValueError("Asset revision previews require asset_history references")
        return []
    history = manifest["asset_history"]
    if (not isinstance(history, dict) or type(history.get("schema_version")) is not int or
            history["schema_version"] != 1 or not isinstance(history.get("assets"), list)):
        raise ValueError("asset_history must contain schema_version 1 and an assets array")
    assets, asset_ids, referenced = [], set(), set()
    for value in history["assets"]:
        if not isinstance(value, dict):
            raise ValueError("Asset history asset must be an object")
        identifier = history_id(value.get("id"), "asset id")
        if identifier in asset_ids:
            raise ValueError("Duplicate asset history asset id")
        asset_ids.add(identifier)
        asset = {"id": identifier, "label": history_text(value.get("label"), "asset label", 100)}
        rows = value.get("revisions")
        if not isinstance(rows, list) or not rows:
            raise ValueError("Each asset history asset needs a nonempty revisions array")
        revisions = {}
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError("Asset history revision must be an object")
            revision_id = history_id(row.get("id"), "revision id")
            if revision_id in revisions:
                raise ValueError("Duplicate revision id within asset history asset")
            preview_path = row.get("preview_path")
            if not isinstance(preview_path, str) or preview_path not in previews:
                raise ValueError("Revision preview_path must reference a verified asset_revision_preview entry")
            if preview_path in referenced:
                raise ValueError("Historical revisions require distinct preview paths")
            referenced.add(preview_path)
            parent = row.get("parent")
            if parent is not None:
                history_id(parent, "parent revision id")
            disposition = row.get("disposition", "candidate")
            if not isinstance(disposition, str) or disposition not in {"candidate", "rejected", "superseded", "retained"}:
                raise ValueError("Unknown asset revision disposition")
            revision = {"id": revision_id, "parent": parent,
                        "direction": history_text(row.get("direction"), "direction", 160),
                        "reason": history_text(row.get("reason"), "revision reason"),
                        "date": row.get("date"), "disposition": disposition,
                        "disposition_explicit": "disposition" in row,
                        "preview": previews[preview_path]}
            revision["date_key"] = history_date(revision["date"])
            revisions[revision_id] = revision
        for revision in revisions.values():
            cursor, seen = revision, set()
            while cursor["parent"] is not None:
                if cursor["id"] in seen or cursor["parent"] == cursor["id"]:
                    raise ValueError("Asset history parent cycle or self-parent")
                seen.add(cursor["id"])
                parent = revisions.get(cursor["parent"])
                if parent is None:
                    raise ValueError("Unknown parent revision in asset history")
                if parent["date_key"] > cursor["date_key"]:
                    raise ValueError("Asset history parent cannot be newer than its child")
                cursor = parent
        for field in ("selected_revision", "integrated_revision"):
            reference = value.get(field)
            if reference is not None:
                history_id(reference, field)
                if reference not in revisions:
                    raise ValueError("Unknown " + field + " in asset history")
            asset[field] = reference
        events = value.get("events", [])
        if not isinstance(events, list):
            raise ValueError("Asset history events must be an array")
        public_events, event_ids = [], set()
        for event in events:
            if not isinstance(event, dict):
                raise ValueError("Asset history event must be an object")
            event_id = history_id(event.get("id"), "event id")
            if event_id in event_ids:
                raise ValueError("Duplicate asset history event id")
            event_ids.add(event_id)
            kind = event.get("type")
            if not isinstance(kind, str) or kind not in {"direction", "selection", "integration", "rejection"}:
                raise ValueError("Unknown asset history event type")
            public = {"id": event_id, "type": kind, "date": event.get("date"),
                      "reason": history_text(event.get("reason"), "event reason")}
            public["date_key"] = history_date(public["date"])
            reference = event.get("revision_id")
            if reference is not None or kind != "direction":
                history_id(reference, "event revision id")
                if reference not in revisions:
                    raise ValueError("Unknown event revision reference in asset history")
                if revisions[reference]["date_key"] > public["date_key"]:
                    raise ValueError("Asset history event cannot precede its referenced revision")
                public["revision_id"] = reference
            if "direction" in event or kind == "direction":
                public["direction"] = history_text(event.get("direction"), "event direction", 160)
            public_events.append(public)
        asset["events"] = sorted(public_events, key=lambda item: item["date_key"])
        for revision in revisions.values():
            if not revision["disposition_explicit"]:
                decisions = [event for event in asset["events"]
                             if event.get("revision_id") == revision["id"] and event["type"] != "direction"]
                if decisions and decisions[-1]["type"] == "rejection":
                    revision["disposition"] = "rejected"
            if revision["id"] == asset["selected_revision"] and revision["disposition"] in {"rejected", "superseded"}:
                raise ValueError("Selected revision cannot have a rejected or superseded disposition")
        asset["revisions"] = sorted(revisions.values(), key=lambda item: item["date_key"])
        assets.append(asset)
    if referenced != set(previews):
        raise ValueError("Unreferenced asset_revision_preview entry; omit it or add its revision")
    return assets


def platform_for(entry, manifest):
    aliases = {"ios": "iOS", "iphone": "iOS", "ipados": "iOS", "android": "Android"}
    explicit = entry.get("platform")
    if isinstance(explicit, str) and explicit:
        return aliases.get(explicit.casefold(), "Unspecified platform")
    parts = entry["path"].split("/")
    if len(parts) > 1 and parts[0] == "stores" and parts[1] in aliases:
        return aliases[parts[1]]
    value = manifest.get("platform")
    return aliases.get(value.casefold(), "Unspecified platform") if isinstance(value, str) else "Unspecified platform"


def locale_for(entry, manifest):
    value = entry.get("locale", "")
    if not value and entry["path"].startswith("stores/"):
        parts = entry["path"].split("/")
        value = parts[2] if len(parts) > 3 else ""
    if not value:
        value = manifest.get("locale", "")
    return value if isinstance(value, str) and re.fullmatch(r"[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*", value) else ""


def media_signature(stream, extension):
    header = stream.read(32)
    stream.seek(0)
    if extension == ".png":
        return header.startswith(b"\x89PNG\r\n\x1a\n")
    if extension in {".jpg", ".jpeg"}:
        return header.startswith(b"\xff\xd8\xff")
    if extension == ".webp":
        return header[:4] == b"RIFF" and header[8:12] == b"WEBP"
    if extension == ".webm":
        return header.startswith(b"\x1aE\xdf\xa3")
    return len(header) >= 12 and header[4:8] in {b"ftyp", b"moov", b"mdat", b"wide", b"free"}


def owned_registry(site):
    registry = read_json(site, REGISTRY)
    if not isinstance(registry, dict) or registry.get("owner") != OWNER or registry.get("schema_version") != 1:
        raise ValueError("Refusing an output directory not owned by this preview builder")
    files = registry.get("files")
    if not isinstance(files, dict) or "index.html" not in files:
        raise ValueError("Invalid generated-file registry")
    for path, digest in files.items():
        if not isinstance(path, str) or not GENERATED_PATH.fullmatch(path) or not isinstance(digest, str) or not re.fullmatch(r"[a-f0-9]{64}", digest):
            raise ValueError("Invalid generated-file registry")
    return registry


def verify_owned_file(site, path, expected):
    with open_regular(site, path) as stream:
        if sha256(stream) != expected:
            raise ValueError("A generated file changed; refusing to overwrite or serve it")


STYLE = """
:root{color-scheme:dark;--bg:#0a111c;--panel:#131e2c;--line:#283647;--text:#f1f5f9;--muted:#a8b6c8;--accent:#78e1c0}
*{box-sizing:border-box}body{margin:0;background:radial-gradient(ellipse at 90% 0,#183438 0,transparent 40%),var(--bg);color:var(--text);font-family:system-ui,-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;line-height:1.55}
a{color:var(--accent);text-underline-offset:4px}button{font:inherit}header,main,footer{max-width:1320px;margin:auto;padding:30px clamp(20px,5vw,64px)}header{padding-top:64px;padding-bottom:16px}.eyebrow{text-transform:uppercase;letter-spacing:.17em;font-size:12px;font-weight:700;color:var(--accent)}h1{font-size:clamp(38px,7vw,76px);font-weight:650;letter-spacing:-.055em;line-height:1.08;margin:18px 0}h2{font-size:27px;letter-spacing:-.025em;margin:0}h3{font-size:17px;margin:0 0 7px}.intro{color:var(--muted);max-width:680px;font-size:17px}.meta,.tags{display:flex;gap:8px;flex-wrap:wrap}.pill{border:1px solid var(--line);padding:5px 12px;border-radius:999px;font-size:12px;color:var(--muted)}.stats{display:flex;gap:30px;margin:26px 0}.stats strong{display:block;font-size:24px;color:var(--text)}.stats span{color:var(--muted);font-size:13px}nav{display:flex;gap:8px;flex-wrap:wrap;margin:28px 0 6px}button{border:1px solid var(--line);border-radius:10px;background:var(--panel);color:var(--muted);cursor:pointer;padding:9px 16px}button:hover,button[aria-pressed=true]{background:var(--accent);border-color:var(--accent);color:#10231f}button:focus-visible,a:focus-visible{outline:3px solid #b7a4ff;outline-offset:4px}
section{margin-bottom:48px}.section-head{display:flex;align-items:baseline;justify-content:space-between;gap:18px;margin-bottom:20px}.section-head p{color:var(--muted);margin:0;font-size:13px}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,245px),1fr));gap:20px}.card{border:1px solid var(--line);background:var(--panel);border-radius:18px;overflow:hidden;min-width:0}.visual{display:flex;align-items:center;justify-content:center;background:#080e18;padding:14px;min-height:160px}.visual img{max-width:100%;height:auto;max-height:550px;object-fit:contain;display:block}.visual video{width:100%;max-height:550px;display:block;background:#080e18}.icons .visual{min-height:230px}.icons img{width:170px;max-height:200px}.caption{padding:18px}.caption p{margin:7px 0 14px;color:var(--muted);font-size:13px}.caption a{font-size:13px}.empty{border:1px dashed var(--line);border-radius:16px;padding:26px;color:var(--muted);margin-top:18px}.copy-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,350px),1fr));gap:20px}.copy{padding:24px}.copy details{border-top:1px solid var(--line);padding:14px 0}.copy summary{cursor:pointer;font-weight:600}.copy pre{font:inherit;font-size:14px;color:#c9d4e2;white-space:pre-wrap;overflow-wrap:anywhere;margin-bottom:0}.copy .tags{margin-bottom:20px}.notice{border-left:3px solid var(--accent);padding:4px 0 4px 18px;color:var(--muted);font-size:14px}footer{border-top:1px solid var(--line);font-size:12px;color:var(--muted);padding-bottom:40px}[hidden]{display:none!important}@media(max-width:600px){header{padding-top:34px}.stats{gap:22px}.section-head{display:block}.section-head p{margin-top:5px}.grid{grid-template-columns:1fr 1fr;gap:12px}.caption{padding:12px}.caption h3{font-size:14px}.visual{padding:7px}.icons img{width:110px}.icons .visual{min-height:160px}}@media(prefers-reduced-motion:no-preference){a,button{transition:color .15s,background .15s}}
"""

SCRIPT = """
document.querySelectorAll('[data-filter]').forEach(button=>button.addEventListener('click',()=>{
  const selected=button.dataset.filter;
  document.querySelectorAll('[data-filter]').forEach(other=>other.setAttribute('aria-pressed',String(other===button)));
  document.querySelectorAll('[data-platform]').forEach(card=>card.hidden=selected!=='all'&&card.dataset.platform!==selected);
  document.querySelectorAll('[data-group]').forEach(section=>{
    const cards=[...section.querySelectorAll('[data-platform]')];
    const message=section.querySelector('.filter-empty');
    if(message) message.hidden=cards.some(card=>!card.hidden);
  });
}));
"""


STYLE += """
.asset-history .asset-group{border-top:1px solid var(--line);padding-top:24px;margin-top:28px}
.asset-history .asset-title{font-size:23px;margin-bottom:10px}.asset-summary{display:flex;gap:10px;flex-wrap:wrap;margin:12px 0 20px}.asset-summary span{border:1px solid var(--line);border-radius:10px;padding:8px 12px;color:var(--muted);font-size:14px}.asset-summary strong{color:var(--text)}
.revision-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:20px;align-items:start}.revision-card h4{font-size:18px;margin:12px 0 6px}.revision-card .visual{height:340px}.revision-card .visual img,.revision-card .visual video{max-height:312px;width:auto;max-width:100%;object-fit:contain}.revision-card.is-selected{border-color:#b7a4ff}.revision-card.is-integrated{box-shadow:inset 0 0 0 2px var(--accent)}.pill.selected{color:#e5d9ff;border-color:#b7a4ff}.pill.integrated{color:var(--accent);border-color:var(--accent)}.revision-card .reason,.history-events p{overflow-wrap:anywhere}.revision-card time{font-size:12px;color:var(--muted)}.history-events{margin:20px 0;padding:18px 22px;border:1px solid var(--line);border-radius:14px}.history-events summary{cursor:pointer;font-weight:600}.history-events ol{padding-left:20px;margin-bottom:0}.history-events li{padding:8px 0}.history-events time{color:var(--muted);font-size:13px}.history-events p{margin:4px 0;color:var(--muted);font-size:14px}
@media(max-width:650px){.revision-grid{grid-template-columns:1fr;gap:16px}.revision-card .visual{height:300px}.revision-card .visual img,.revision-card .visual video{max-height:278px}.asset-summary{display:grid;grid-template-columns:1fr}.revision-card .caption{padding:18px}}
"""


def render_asset_history(assets):
    if not assets:
        return ""
    escape = lambda value: html.escape(str(value), quote=True)
    groups = []
    for asset in assets:
        cards = []
        for revision in asset["revisions"]:
            item = revision["preview"]
            selected = revision["id"] == asset["selected_revision"]
            integrated = revision["id"] == asset["integrated_revision"]
            badges = []
            if selected:
                badges.append('<span class="pill selected">Selected</span>')
            if integrated:
                badges.append('<span class="pill integrated">Integrated</span>')
            if not selected and not integrated or revision["disposition"] != "candidate":
                badges.append('<span class="pill">' + escape(revision["disposition"].capitalize()) + '</span>')
            title = asset["label"] + " · " + revision["id"]
            src = escape(item["public_path"])
            if item["video"]:
                visual = '<video controls playsinline preload="metadata" aria-label="' + escape(title) + '"><source src="' + src + '" type="' + MIME[item["extension"]] + '">Download the preview to view it.</video>'
            else:
                visual = '<a href="' + src + '" target="_blank" rel="noopener"><img src="' + src + '" loading="lazy" alt="' + escape(title + " · " + revision["direction"]) + '"></a>'
            parent = "From " + revision["parent"] if revision["parent"] else "No parent recorded"
            css = "card revision-card" + (" is-selected" if selected else "") + (" is-integrated" if integrated else "")
            cards.append('<article class="' + css + '" data-revision="' + escape(revision["id"]) + '" data-platform="' + escape(item["platform"]) + '"><div class="visual">' + visual + '</div><div class="caption"><div class="tags">' + "".join(badges) + '</div><h4>' + escape(revision["id"] + " · " + revision["direction"]) + '</h4><time datetime="' + escape(revision["date"]) + '">' + 'Recorded ' + escape(revision["date"]) + '</time><p>' + escape(parent + " · " + item["platform"]) + '</p><p class="reason">' + escape(revision["reason"]) + '</p><a href="' + src + '" download>Download review preview</a></div></article>')
        events = []
        for event in asset["events"]:
            title = event["type"].capitalize()
            if "revision_id" in event:
                title += " · " + event["revision_id"]
            if "direction" in event:
                title += " · " + event["direction"]
            events.append('<li><time datetime="' + escape(event["date"]) + '">' + escape(event["date"]) + '</time><br><strong>' + escape(title) + '</strong><p>' + escape(event["reason"]) + '</p></li>')
        timeline = '<details class="history-events" open><summary>Direction and decision history</summary><ol>' + "".join(events) + '</ol></details>' if events else '<p class="intro">No public decision events included.</p>'
        selected = asset["selected_revision"] or "Not recorded"
        integrated = asset["integrated_revision"] or "Not recorded"
        groups.append('<section class="asset-group" data-group data-asset-id="' + escape(asset["id"]) + '"><h3 class="asset-title">' + escape(asset["label"]) + '</h3><div class="asset-summary"><span>Current selection: <strong>' + escape(selected) + '</strong></span><span>Integrated in app: <strong>' + escape(integrated) + '</strong></span></div><div class="revision-grid">' + "".join(cards) + '</div><p class="empty filter-empty" hidden>No matching review previews for this platform.</p>' + timeline + '</section>')
    return '<section class="asset-history"><div class="section-head"><h2>Asset revision history</h2><p>Compare candidates and follow changes in direction</p></div><p class="notice">Selection and integration are separate recorded states. Choosing a candidate does not mean it is in the app; this gallery does not change either state.</p>' + "".join(groups) + '</section>'


def render_page(manifest, media, copies, history=None):
    escape = lambda value: html.escape(str(value), quote=True)
    app = safe_label(manifest.get("app"), "App release")
    build = manifest.get("build") if isinstance(manifest.get("build"), dict) else {}
    badges = []
    for key, label in (("version", "Version"), ("build", "Build")):
        value = safe_label(build.get(key), "", 40)
        if value:
            badges.append('<span class="pill">' + label + " " + escape(value) + "</span>")
    platforms = sorted({item["platform"] for item in media + copies})
    badges.extend('<span class="pill">' + escape(platform) + "</span>" for platform in platforms)
    nav = ""
    if len(platforms) > 1:
        nav = '<nav aria-label="Filter by platform"><button data-filter="all" aria-pressed="true">All platforms</button>'
        nav += "".join('<button data-filter="' + escape(p) + '" aria-pressed="false">' + escape(p) + "</button>" for p in platforms) + "</nav>"
    groups = [("Icons", "icons", "App and store identities", ICON_KINDS),
              ("Store gallery", "", "Screenshots, previews and posters", {"app_store_screenshot", "app_store_preview", "preview_poster"}),
              ("Promotional assets", "", "Separate campaign images and video", {"promo_image", "promo_video"})]
    labels = {"app_store_screenshot": "Screenshot", "app_store_preview": "Store preview", "preview_poster": "Preview poster",
              "promo_image": "Promo image", "promo_video": "Promo video", "app_icon": "App icon", "store_icon": "Store icon", "launcher_icon": "Launcher icon"}
    content = [render_asset_history(history or [])]
    for heading, css, subheading, kinds in groups:
        items = [item for item in media if item["kind"] in kinds]
        cards = []
        for number, item in enumerate(items, 1):
            title = labels[item["kind"]] + " " + str(number)
            src = escape(item["public_path"])
            visual = ('<video controls playsinline preload="metadata" aria-label="' + escape(title) + '"><source src="' + src + '" type="' + MIME[item["extension"]] + '">Your browser cannot play this format. Use the download link.</video>') if item["video"] else ('<a href="' + src + '" target="_blank" rel="noopener"><img src="' + src + '" loading="lazy" alt="' + escape(title + " · " + item["platform"]) + '"></a>')
            detail = item["platform"] + (" · " + item["locale"] if item["locale"] else "")
            cards.append('<article class="card" data-platform="' + escape(item["platform"]) + '"><div class="visual">' + visual + '</div><div class="caption"><h3>' + escape(title) + '</h3><p>' + escape(detail) + '</p><a href="' + src + '" download>Download ' + ("video" if item["video"] else "image") + '</a></div></article>')
        empty = "No " + heading.lower() + " are included in this verified package."
        content.append('<section data-group><div class="section-head"><h2>' + heading + '</h2><p>' + subheading + '</p></div><div class="grid ' + css + '">' + "".join(cards) + '</div><p class="empty filter-empty"' + (' hidden' if cards else '') + '>' + ("No matching assets for this platform." if cards else empty) + '</p></section>')
    copy_cards = []
    for item in copies:
        title = item["platform"] + (" · " + item["locale"] if item["locale"] else "")
        sections = "".join('<details open><summary>' + escape(heading) + '</summary><pre>' + escape(body) + '</pre></details>' for heading, body in item["sections"])
        copy_cards.append('<article class="card copy" data-platform="' + escape(item["platform"]) + '"><h3>' + escape(title) + '</h3><p><a href="' + escape(item["public_path"]) + '" download="public-store-copy.txt">Download public copy</a></p>' + sections + '</article>')
    content.append('<section data-group><div class="section-head"><h2>Store copy</h2><p>Public listing text only</p></div><div class="copy-grid">' + "".join(copy_cards) + '</div><p class="empty filter-empty"' + (' hidden' if copies else '') + '>' + ("No matching copy for this platform." if copies else "No public listing sections are included. Add verified store_copy or explicitly authored preview_copy to the manifest.") + '</p></section>')
    return '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="' + escape(CSP) + '"><meta name="referrer" content="no-referrer"><title>' + escape(app) + ' · Release preview</title><style>' + STYLE + '</style></head><body><header><div class="eyebrow">ShippyKit / Release preview</div><h1>' + escape(app) + '</h1><p class="intro">A closer look at the app. Explore its store images, watch the previews, and read the public listing.</p><div class="meta">' + "".join(badges) + '</div><div class="stats"><span><strong>' + str(sum(not i["video"] for i in media)) + '</strong>images</span><span><strong>' + str(sum(i["video"] for i in media)) + '</strong>videos</span><span><strong>' + str(len(copies)) + '</strong>public listings</span></div><p class="notice">Prepared release assets. This preview does not establish an upload, approval, or public store release.</p>' + nav + '</header><main>' + "".join(content) + '</main><footer>Built locally with ShippyKit. Only selected, hash-verified public assets and public listing sections are included. No external fonts, scripts or analytics.</footer><script>' + SCRIPT + '</script></body></html>'


def build(release_output, output=None):
    supplied_root = Path(release_output).expanduser().absolute()
    if supplied_root.is_symlink():
        raise ValueError("Release output cannot be a symlink")
    root = supplied_root.resolve()
    manifest = read_json(root, "manifest.json")
    if not isinstance(manifest, dict) or not isinstance(manifest.get("files"), list):
        raise ValueError("Manifest must contain a files array")
    site = Path(output).expanduser().absolute() if output is not None else root / "site"
    if site.is_symlink():
        raise ValueError("Output cannot be a symlink")
    site = site.parent.resolve() / site.name
    previous = None
    if site.exists():
        try:
            previous = owned_registry(site)
        except (ValueError, OSError, json.JSONDecodeError) as error:
            raise ValueError("Refusing an output directory not owned by this preview builder") from error
        for path, digest in previous["files"].items():
            if (site / path).exists() or (site / path).is_symlink():
                verify_owned_file(site, path, digest)
    site.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".shippykit-preview-", dir=str(site.parent)))
    (staging / "assets").mkdir()
    media, copies, generated = [], [], {}
    try:
        for number, entry in enumerate(manifest["files"], 1):
            if not isinstance(entry, dict) or not isinstance(entry.get("kind"), str) or entry["kind"] not in MEDIA_KINDS | COPY_KINDS:
                continue
            try:
                parts = relative_parts(entry.get("path"))
                if any(part.startswith(".") or part.casefold() in PRIVATE_PARTS for part in parts) or parts[-1].casefold() in PRIVATE_DOCUMENTS:
                    raise ValueError("Private source locations are never preview assets")
                if entry["kind"] == "asset_revision_preview":
                    if parts[:2] != ["artwork", "review"] or any(part.casefold() in {"masters", "prompts"} for part in parts):
                        raise ValueError("Asset revision previews must be sanitized exports under artwork/review/")
                    if type(entry.get("bytes")) is not int or entry["bytes"] <= 0:
                        raise ValueError("Asset revision previews require an explicit positive byte size")
                expected = entry.get("sha256")
                if not isinstance(expected, str) or not re.fullmatch(r"[a-fA-F0-9]{64}", expected):
                    raise ValueError("Public assets require a SHA-256 provenance hash")
                expected = expected.lower()
                extension = PurePosixPath(entry["path"]).suffix.lower()
                is_copy = entry["kind"] in COPY_KINDS
                if is_copy and extension not in {".md", ".txt"}:
                    raise ValueError("Public copy must be Markdown or plain text")
                if not is_copy and extension not in MIME.keys() - {".html", ".txt"}:
                    raise ValueError("Unsupported public media format")
                with open_regular(root, entry["path"]) as stream:
                    size = os.fstat(stream.fileno()).st_size
                    if size == 0 or ("bytes" in entry and entry["bytes"] != size) or sha256(stream) != expected:
                        raise ValueError("Public asset size/hash verification failed")
                    stream.seek(0)
                    common = {"platform": platform_for(entry, manifest), "locale": locale_for(entry, manifest)}
                    if is_copy:
                        if size > 1024 * 1024:
                            raise ValueError("Public copy exceeds 1 MiB")
                        text = stream.read().decode("utf-8-sig")
                        sections = [("Public copy", text.strip())] if entry["kind"] == "preview_copy" and text.strip() else store_sections(text, safe_label(manifest.get("app"), "App release"))
                        if not sections:
                            continue
                        data = ("\n\n".join(heading + "\n" + body for heading, body in sections) + "\n").encode("utf-8")
                        digest = hashlib.sha256(data).hexdigest()
                        public_path = "assets/" + digest + ".txt"
                        (staging / public_path).write_bytes(data)
                        copies.append({**common, "sections": sections, "public_path": public_path})
                    else:
                        if not media_signature(stream, extension):
                            raise ValueError("Media contents do not match the declared format")
                        public_path = "assets/" + expected + extension
                        with (staging / public_path).open("wb") as destination:
                            shutil.copyfileobj(stream, destination)
                        with (staging / public_path).open("rb") as copied:
                            digest = sha256(copied)
                        if digest != expected:
                            raise ValueError("Asset changed during copy")
                        media.append({**common, "kind": entry["kind"], "extension": extension,
                                      "video": MIME[extension].startswith("video/"), "public_path": public_path,
                                      "source_path": entry["path"]})
                    generated[public_path] = digest
            except (ValueError, OSError, UnicodeError) as error:
                raise ValueError("Public manifest entry {}: {}".format(number, error)) from error
        history = asset_history(manifest, media)
        page = render_page(manifest, media, copies, history).encode("utf-8")
        (staging / "index.html").write_bytes(page)
        generated["index.html"] = hashlib.sha256(page).hexdigest()
        counts = {"images": sum(not item["video"] for item in media), "videos": sum(item["video"] for item in media), "public_listings": len(copies),
                  "asset_groups": len(history), "asset_revisions": sum(len(asset["revisions"]) for asset in history)}
        registry = {"owner": OWNER, "schema_version": 1, "files": generated, "counts": counts}
        (staging / REGISTRY).write_text(json.dumps(registry, indent=2) + "\n", encoding="utf-8")
        if previous is None:
            os.replace(staging, site)
        else:
            for path in generated:
                target = site / path
                if target.exists() and path not in previous["files"]:
                    raise ValueError("Refusing to overwrite an unrelated output file")
                if target.is_symlink() or target.parent.is_symlink():
                    raise ValueError("Output contains a symlink")
            for path in generated:
                target = site / path
                target.parent.mkdir(parents=True, exist_ok=True)
                os.replace(staging / path, target)
            for path in previous["files"].keys() - generated.keys():
                (site / path).unlink(missing_ok=True)
            os.replace(staging / REGISTRY, site / REGISTRY)
        return {"site": str(site), **counts}
    finally:
        if staging.exists():
            shutil.rmtree(staging)


def byte_range(header, size):
    match = re.fullmatch(r"bytes=(\d*)-(\d*)", header.strip())
    if not match or not any(match.groups()) or size <= 0:
        raise ValueError("Invalid byte range")
    start, end = match.groups()
    if not start:
        length = int(end)
        if length <= 0:
            raise ValueError("Invalid byte range")
        return max(0, size - length), size - 1
    start, end = int(start), int(end) if end else size - 1
    if start >= size or end < start:
        raise ValueError("Invalid byte range")
    return start, min(end, size - 1)


def make_server(site, port=8765):
    site = Path(site).expanduser().absolute()
    if site.is_symlink():
        raise ValueError("Site cannot be a symlink")
    site = site.resolve()
    registry = owned_registry(site)
    for path, digest in registry["files"].items():
        verify_owned_file(site, path, digest)

    class Handler(BaseHTTPRequestHandler):
        server_version = "ShippyKitPreview"
        sys_version = ""

        def log_message(self, *_args):
            pass

        def do_GET(self):
            self.deliver(False)

        def do_HEAD(self):
            self.deliver(True)

        def missing(self):
            self.send_response(404)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def deliver(self, head):
            try:
                url = urlsplit(self.path)
                if url.scheme or url.netloc or re.search(r"%(?![0-9a-fA-F]{2})", url.path):
                    return self.missing()
                path = unquote(url.path, errors="strict")
                if not path.startswith("/") or path.startswith("//"):
                    return self.missing()
                relative = "index.html" if path == "/" else path[1:]
                expected = registry["files"].get(relative)
                if expected is None:
                    return self.missing()
                with open_regular(site, relative) as stream:
                    if sha256(stream) != expected:
                        return self.missing()
                    size = os.fstat(stream.fileno()).st_size
                    start, end, code = 0, size - 1, 200
                    requested = self.headers.get("Range") if not head else None
                    if requested and self.headers.get("If-Range", '"' + expected + '"') == '"' + expected + '"':
                        try:
                            start, end = byte_range(requested, size)
                            code = 206
                        except ValueError:
                            self.send_response(416)
                            self.send_header("Content-Range", "bytes */" + str(size))
                            self.send_header("Content-Length", "0")
                            self.end_headers()
                            return
                    self.send_response(code)
                    self.send_header("Content-Type", MIME[Path(relative).suffix])
                    self.send_header("Content-Length", str(end - start + 1))
                    self.send_header("Accept-Ranges", "bytes")
                    self.send_header("ETag", '"' + expected + '"')
                    self.send_header("Cache-Control", "no-store")
                    self.send_header("X-Content-Type-Options", "nosniff")
                    self.send_header("Referrer-Policy", "no-referrer")
                    self.send_header("Content-Security-Policy", CSP)
                    if code == 206:
                        self.send_header("Content-Range", "bytes {}-{}/{}".format(start, end, size))
                    self.end_headers()
                    if not head:
                        stream.seek(start)
                        remaining = end - start + 1
                        while remaining:
                            chunk = stream.read(min(1024 * 1024, remaining))
                            if not chunk:
                                break
                            self.wfile.write(chunk)
                            remaining -= len(chunk)
            except ConnectionError:
                # Browsers routinely cancel video ranges while seeking or closing
                # a tab. The connection is gone; do not attempt a second response.
                return
            except (OSError, ValueError, UnicodeError):
                self.missing()

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    builder = commands.add_parser("build", help="Create a public-only static preview")
    builder.add_argument("--release-output", type=Path, default=Path("release-output"))
    builder.add_argument("--output", type=Path)
    server = commands.add_parser("serve", help="Serve only generated preview files on loopback")
    server.add_argument("--site", type=Path, default=Path("release-output/site"))
    server.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    try:
        if args.command == "build":
            result = build(args.release_output, args.output)
            print(json.dumps(result, indent=2))
            print("Open " + (Path(result["site"]) / "index.html").as_uri())
            print("Restart any preview server after rebuilding.")
        else:
            if not 1 <= args.port <= 65535:
                raise ValueError("Port must be between 1 and 65535")
            with make_server(args.site, args.port) as httpd:
                print("Preview: http://127.0.0.1:{}/ (Ctrl-C to stop)".format(httpd.server_port), flush=True)
                try:
                    httpd.serve_forever()
                except KeyboardInterrupt:
                    print("\nPreview stopped.")
    except (OSError, ValueError, json.JSONDecodeError) as error:
        parser.exit(1, "Preview failed: " + str(error) + "\n")


if __name__ == "__main__":
    main()
