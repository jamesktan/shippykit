#!/usr/bin/env node
import crypto from "node:crypto";
// Portable ShippyKit Google Play uploader. Node 18+, no dependencies.
// Google reference: https://developers.google.com/android-publisher/edits
// Scope: one edit holding a signed AAB on a testing track, listing text and listing images. Never production.
import fs from "node:fs";
import path from "node:path";
import { pathToFileURL } from "node:url";
import { imageInfo, noSymlink, Receipt, sourceFile } from "./apple-upload.mjs";

const API = "https://androidpublisher.googleapis.com/androidpublisher/v3/applications/";
const UPLOAD = "https://androidpublisher.googleapis.com/upload/androidpublisher/v3/applications/";
const HOSTS = new Set(["androidpublisher.googleapis.com", "www.googleapis.com"]);
const TOKEN_URI = "https://oauth2.googleapis.com/token";
const SCOPE = "https://www.googleapis.com/auth/androidpublisher";
const PARTS = ["bundle", "listing", "images"];
const TEXT = ["title", "shortDescription", "fullDescription"];
const LIMITS = { title: 30, shortDescription: 80, fullDescription: 4000, releaseNotes: 500 };
const HEADINGS = {
  name: "title",
  title: "title",
  "short description": "shortDescription",
  description: "fullDescription",
  "full description": "fullDescription",
  "release notes": "releaseNotes",
};
const SCREENSHOTS = new Set(["phoneScreenshots", "sevenInchScreenshots", "tenInchScreenshots", "tvScreenshots", "wearScreenshots"]);
const SINGLE = { icon: [512, 512], featureGraphic: [1024, 500], tvBanner: [1280, 720] };
const RETRY = new Set([429, 500, 502, 503, 504]);
const CHUNK = 8 * 1024 * 1024; // resumable chunks must be multiples of 256 KiB
const LOCALE = /^[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*$/;
const hash = (bytes) => crypto.createHash("sha256").update(bytes).digest("hex");
const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const chars = (text) => [...text].length;
const clean = (text) =>
  String(text ?? "")
    .replace(/\r\n?/g, "\n")
    .trim();
const sameCodes = (a = [], b = []) => a.map(String).sort().join() === b.map(String).sort().join();
const sameList = (a, b) => a.length === b.length && a.every((x, i) => x === b[i]);
const sameNotes = (a = [], b = []) => {
  const key = (notes) => JSON.stringify(notes.map((n) => [n.language, clean(n.text)]).sort());
  return key(a) === key(b);
};
const check = (condition, message) => {
  if (!condition) throw new Error(message);
};
export class Pending extends Error {
  constructor(message) {
    super(message);
    this.name = "Pending";
  }
}
export class APIError extends Error {
  constructor(status, reasons, detail) {
    super(`Google Play HTTP ${status}: ${reasons.join(", ") || "request failed"}${detail ? ` (${String(detail).slice(0, 300)})` : ""}`);
    this.status = status;
    this.reasons = reasons;
  }
}

export function parseArgs(argv) {
  const command = argv.shift();
  if (!command || command === "--help" || command === "help") return { help: true };
  check(["plan", "status", "upload"].includes(command), "Expected plan, status, or upload");
  const values = { command };
  const flags = new Set(["replace", "commit"]);
  const names = new Set([
    "release-output",
    "package",
    "version-code",
    "track",
    "status",
    "parts",
    "locales",
    "release-name",
    "receipt",
    "aab",
    "aab-sha256",
  ]);
  while (argv.length) {
    const arg = argv.shift();
    check(arg.startsWith("--"), `Unexpected argument ${arg}`);
    const name = arg.slice(2);
    check(!(name in values), `Duplicate option ${arg}`);
    if (flags.has(name)) values[name] = true;
    else {
      check(names.has(name), `Unknown option ${arg}`);
      const value = argv.shift();
      check(value && !value.startsWith("--"), `Missing value for ${arg}`);
      values[name] = value;
    }
  }
  check(values.package, "Required --package");
  check(/^[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z][A-Za-z0-9_]*)+$/.test(values.package), "Invalid package name");
  if (values["version-code"])
    check(/^[1-9]\d{0,9}$/.test(values["version-code"]) && Number(values["version-code"]) <= 2100000000, "Invalid version-code");
  values.track ??= "internal";
  check(/^[A-Za-z0-9][A-Za-z0-9:_ .-]{0,99}$/.test(values.track), "Invalid track");
  check(!/(^|:)production$/i.test(values.track), "Production is not released by this helper; use Play Console under a release instruction");
  values.status ??= "draft";
  check(["draft", "completed"].includes(values.status), "Release status must be draft or completed");
  check(command !== "upload" || values.parts, "Required --parts for upload: any of bundle,listing,images");
  values.parts = values.parts ? values.parts.split(",") : [...PARTS];
  check(
    values.parts.every((p) => PARTS.includes(p)) && new Set(values.parts).size === values.parts.length,
    "Invalid --parts; use bundle,listing,images",
  );
  values.locales = values.locales ? values.locales.split(",") : null;
  check(!values.locales || values.locales.every((l) => LOCALE.test(l)), "Invalid --locales");
  check(!values["release-name"] || chars(values["release-name"]) <= 50, "Release name exceeds 50 characters");
  check(!values.commit || command === "upload", "--commit applies only to upload");
  check(!values.aab === !values["aab-sha256"], "--aab and --aab-sha256 go together");
  values["release-output"] = path.resolve(values["release-output"] ?? "release-output");
  values.receipt = path.resolve(values.receipt ?? path.join(values["release-output"], "play-upload-receipt.json"));
  return values;
}

export function parseListing(markdown) {
  const fields = {};
  let field = null;
  let fence = false;
  for (const line of markdown.replace(/\r\n?/g, "\n").split("\n")) {
    if (/^\s{0,3}(?:`{3,}|~{3,})/.test(line)) {
      check(!field, "Store listing fields are plain text; move fenced blocks out of public sections");
      fence = !fence;
      continue;
    }
    const heading = fence ? null : /^\s{0,3}#{1,6}\s+(.+?)(?:\s+#+)?\s*$/.exec(line);
    if (heading) {
      const name = heading[1].replace(/\s+/g, " ").replace(/’/g, "'").toLowerCase();
      field = HEADINGS[name] ?? (/^what's new(?:\s|$)/.test(name) ? "releaseNotes" : null);
      check(!field || !(field in fields), `Duplicate ${field} section`);
      if (field) fields[field] = [];
    } else if (field && !fence) fields[field].push(line);
  }
  return Object.fromEntries(
    Object.entries(fields)
      .map(([k, lines]) => [k, lines.join("\n").trim()])
      .filter(([, v]) => v),
  );
}
export function checkImage(type, info, size) {
  const { width: w, height: h } = info;
  if (type === "icon") {
    check(
      info.extension === ".png" && info.alpha && w === 512 && h === 512 && size <= 1024 * 1024,
      "Play icon must be a 512x512 32-bit PNG with alpha, at most 1024 KB",
    );
    return;
  }
  check(!info.alpha, `${type} must be an opaque JPEG or 24-bit PNG`);
  if (type in SINGLE) check(w === SINGLE[type][0] && h === SINGLE[type][1], `${type} must be ${SINGLE[type].join("x")}, not ${w}x${h}`);
  else {
    const [short, long] = [Math.min(w, h), Math.max(w, h)];
    check(short >= 320 && long <= 3840 && long <= 2 * short, `Screenshot ${w}x${h} is outside Play's 320-3840 px sides or 2:1 ratio`);
  }
}
export function zipEntries(bytes) {
  let end = -1;
  for (let i = bytes.length - 22; i >= Math.max(0, bytes.length - 65557); i--)
    if (bytes.readUInt32LE(i) === 0x06054b50) {
      end = i;
      break;
    }
  check(end >= 0, "AAB is not a readable ZIP archive");
  const count = bytes.readUInt16LE(end + 10);
  let offset = bytes.readUInt32LE(end + 16);
  check(count !== 0xffff && offset !== 0xffffffff, "ZIP64 bundles are not supported by this verifier; inspect it with bundletool");
  const names = [];
  for (let i = 0; i < count; i++) {
    check(offset + 46 <= bytes.length && bytes.readUInt32LE(offset) === 0x02014b50, "Truncated AAB central directory");
    const length = bytes.readUInt16LE(offset + 28);
    check(offset + 46 + length <= bytes.length, "Truncated AAB central directory");
    names.push(bytes.toString("utf8", offset + 46, offset + 46 + length));
    offset += 46 + length + bytes.readUInt16LE(offset + 30) + bytes.readUInt16LE(offset + 32);
  }
  return names;
}
export function verifyBundle(filename, expectedHash) {
  check(filename && /^[a-f0-9]{64}$/.test(expectedHash ?? ""), "A signed AAB and its SHA-256 are required");
  noSymlink(filename);
  check(fs.statSync(filename).isFile(), "AAB must be a regular file");
  const bytes = fs.readFileSync(filename);
  check(hash(bytes) === expectedHash, "AAB hash mismatch");
  const entries = zipEntries(bytes);
  check(
    entries.every((x) => !x.startsWith("/") && !x.includes("\\") && !x.split("/").includes("..")),
    "Unsafe AAB archive paths",
  );
  check(
    entries.includes("BundleConfig.pb") && entries.includes("base/manifest/AndroidManifest.xml"),
    "Not an Android App Bundle: BundleConfig.pb and base/manifest/AndroidManifest.xml are required",
  );
  // Play requires the registered upload key's JAR signature; it reads the package and versionCode itself.
  check(
    entries.some((x) => /^META-INF\/[^/]+\.(?:RSA|EC|DSA)$/i.test(x)),
    "AAB has no JAR signature; sign it with the registered upload key",
  );
  return { bytes, sha256: expectedHash, size: bytes.length };
}

const android = (item) => item.platform === "android" || (!item.platform && /^stores\/android\//.test(item.path ?? ""));
function storeFile(root, item, label) {
  check(!/(^|\/)(captures|builds|logs|profiles|private)(\/|$)/i.test(item.path), `${label} must be a curated store artifact: ${item.path}`);
  const file = sourceFile(root, item.path);
  const bytes = fs.readFileSync(file);
  check(/^[a-f0-9]{64}$/.test(item.sha256 ?? "") && hash(bytes) === item.sha256, `${label} hash mismatch: ${item.path}`);
  check(item.bytes === undefined || item.bytes === bytes.length, `${label} byte count mismatch: ${item.path}`);
  return { file, bytes };
}
function localeOf(item, manifest) {
  const locale = item.locale ?? /^stores\/android\/([^/]+)\//.exec(item.path)?.[1] ?? manifest.locale;
  check(typeof locale === "string" && LOCALE.test(locale), `Locale is missing or invalid: ${item.path}`);
  return locale;
}
export function loadInputs(options) {
  const root = options["release-output"];
  const raw = fs.readFileSync(sourceFile(root, "manifest.json"));
  const manifest = JSON.parse(raw);
  const entries = manifest.files ?? manifest.artifacts;
  check(Array.isArray(entries), "Manifest needs a files or artifacts array");
  const wanted = (locale) => !options.locales || options.locales.includes(locale);
  const errors = [];
  // status reports invalid local inputs; plan and upload stop on the ones their parts depend on.
  const attempt = (parts, load, fallback) => {
    try {
      return load();
    } catch (error) {
      if (options.command !== "status" && parts.some((p) => options.parts.includes(p))) throw error;
      errors.push({ parts, reason: error.message });
      return fallback;
    }
  };
  const listings = attempt(
    ["listing", "bundle"],
    () => {
      const out = new Map();
      for (const item of entries.filter((x) => x.kind === "store_copy" && android(x))) {
        const locale = localeOf(item, manifest);
        if (!wanted(locale)) continue;
        check(!out.has(locale), `Duplicate Android listing for ${locale}`);
        const fields = parseListing(storeFile(root, item, "Listing").bytes.toString("utf8"));
        for (const [k, v] of Object.entries(fields))
          check(chars(v) <= LIMITS[k], `${locale} ${k} is ${chars(v)} characters; Play allows ${LIMITS[k]}`);
        out.set(locale, { path: item.path, fields });
      }
      return out;
    },
    new Map(),
  );
  const images = attempt(["images"], () => {
    const groups = new Map();
    entries.forEach((item, index) => {
      if (item.play_image_type === undefined) return;
      check(android(item), `play_image_type needs an Android entry: ${item.path}`);
      const type = item.play_image_type;
      check(SCREENSHOTS.has(type) || type in SINGLE, `Unknown play_image_type ${type}`);
      const locale = localeOf(item, manifest);
      if (!wanted(locale)) return;
      const { file, bytes } = storeFile(root, item, "Image");
      const info = imageInfo(bytes);
      if (item.media?.width)
        check(
          item.media.width === info.width && item.media.height === info.height,
          `Image dimensions disagree with manifest: ${item.path}`,
        );
      checkImage(type, info, bytes.length);
      const key = `${locale}/${type}`;
      if (!groups.has(key)) groups.set(key, { locale, type, items: [] });
      groups.get(key).items.push({ file, sha256: item.sha256, extension: info.extension, order: item.order ?? item.storeOrder ?? index });
    });
    for (const group of groups.values()) {
      group.items.sort((a, b) => a.order - b.order);
      const max = SCREENSHOTS.has(group.type) ? 8 : 1;
      check(group.items.length <= max, `${group.locale} ${group.type} holds at most ${max}`);
      check(new Set(group.items.map((x) => x.sha256)).size === group.items.length, `Duplicate image in ${group.locale} ${group.type}`);
    }
    return [...groups.values()];
  }, []);
  const spec = manifest.android_bundle;
  const bundle = attempt(
    ["bundle"],
    () => {
      if (options.aab) return verifyBundle(path.resolve(options.aab), options["aab-sha256"]);
      if (!spec?.path) return null;
      check(
        typeof spec.path === "string" && !path.isAbsolute(spec.path) && !spec.path.split(/[\\/]/).includes(".."),
        "Unsafe android_bundle path",
      );
      check(!spec.package_name || spec.package_name === options.package, "Manifest android_bundle package differs from --package");
      check(
        spec.version_code === undefined || !options["version-code"] || String(spec.version_code) === options["version-code"],
        "Manifest android_bundle version_code differs from --version-code",
      );
      return verifyBundle(path.resolve(root, spec.path), spec.sha256);
    },
    null,
  );
  const versionCode = options["version-code"] ?? (!options.aab && spec?.version_code !== undefined ? String(spec.version_code) : null);
  check(!versionCode || /^[1-9]\d{0,9}$/.test(versionCode), "Invalid android_bundle version_code");
  return { manifestSha256: hash(raw), listings, images, bundle, versionCode, errors };
}
function requireInputs(options, input) {
  if (options.parts.includes("bundle")) {
    check(input.bundle, "The bundle part needs android_bundle in the manifest, or --aab with --aab-sha256");
    check(input.versionCode, "The bundle part needs --version-code or android_bundle.version_code");
  }
  if (options.parts.includes("listing"))
    check(
      [...input.listings.values()].some((l) => TEXT.some((k) => l.fields[k])),
      "The listing part needs an Android store_copy entry with Title, Short description or Description",
    );
  if (options.parts.includes("images")) check(input.images.length, "The images part needs Android manifest entries with play_image_type");
}

export function credentials(env = process.env) {
  const keyPath = env.PLAY_SERVICE_ACCOUNT_KEY || env.GOOGLE_APPLICATION_CREDENTIALS || env.EMBER_PLAY_KEY;
  check(keyPath, "Service-account key reference PLAY_SERVICE_ACCOUNT_KEY (or GOOGLE_APPLICATION_CREDENTIALS) is required");
  return { keyPath };
}
export function serviceAccountToken(auth, fetcher = fetch) {
  let cached = null;
  return async () => {
    if (cached && cached.expires > Date.now() + 300000) return cached.value;
    noSymlink(auth.keyPath);
    const key = JSON.parse(fs.readFileSync(auth.keyPath, "utf8"));
    check(key.type === "service_account" && key.client_email && key.private_key, "Key file is not a Google service-account key");
    check(!key.token_uri || key.token_uri === TOKEN_URI, "Refusing an unexpected service-account token URI");
    const encode = (x) => Buffer.from(JSON.stringify(x)).toString("base64url");
    const now = Math.floor(Date.now() / 1000);
    const input = `${encode({ alg: "RS256", typ: "JWT" })}.${encode({ iss: key.client_email, scope: SCOPE, aud: TOKEN_URI, iat: now, exp: now + 3600 })}`;
    const assertion = `${input}.${crypto.sign("sha256", Buffer.from(input), key.private_key).toString("base64url")}`;
    const response = await fetcher(TOKEN_URI, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({ grant_type: "urn:ietf:params:oauth:grant-type:jwt-bearer", assertion }).toString(),
      redirect: "error",
      signal: AbortSignal.timeout(30000),
    });
    const doc = await response.json().catch(() => ({}));
    if (!response.ok || !doc.access_token)
      throw new Error(
        `Google token HTTP ${response.status}: ${doc.error ?? "no access token"}; check the key and its Play Console invitation`,
      );
    cached = { value: doc.access_token, expires: Date.now() + (doc.expires_in ?? 3600) * 1000 };
    return cached.value;
  };
}
async function apiError(response) {
  const error = (await response.json().catch(() => ({}))).error ?? {};
  const reasons = [error.status, ...(error.errors ?? []).map((e) => e.reason), ...(error.details ?? []).map((d) => d.reason)];
  return new APIError(response.status, [...new Set(reasons.filter(Boolean))], error.message);
}
function googleURL(value) {
  const url = new URL(value);
  check(url.protocol === "https:" && HOSTS.has(url.hostname) && !url.username && !url.password, "Refusing non-Google Play API URL");
  return url;
}
export function createAPI(packageName, token, fetcher = fetch, sleep = wait) {
  const send = async (url, { method = "GET", json, body, headers = {}, timeout = 60000, retry = true }) => {
    googleURL(url);
    for (let attempt = 1; ; attempt++) {
      const response = await fetcher(url, {
        method,
        headers: {
          Authorization: `Bearer ${await token()}`,
          ...(json === undefined ? {} : { "Content-Type": "application/json" }),
          ...headers,
        },
        body: json === undefined ? body : JSON.stringify(json),
        redirect: "manual",
        signal: AbortSignal.timeout(timeout),
      });
      if (!retry || !RETRY.has(response.status) || attempt === 4) return response;
      const after = Number(response.headers.get("retry-after"));
      await response.body?.cancel();
      await sleep(Math.min(60, after > 0 ? after : 2 ** attempt) * 1000);
    }
  };
  const api = async (apiPath, { upload = false, query = {}, raw = false, ...init } = {}) => {
    const url = new URL(`${upload ? UPLOAD : API}${encodeURIComponent(packageName)}${apiPath}`);
    for (const [k, v] of Object.entries(query)) url.searchParams.set(k, v);
    const response = await send(url, init);
    if (!response.ok) throw await apiError(response);
    if (raw) return response;
    const text = await response.text();
    try {
      return text ? JSON.parse(text) : {};
    } catch {
      throw new Error(`Google Play HTTP ${response.status}: invalid JSON response`);
    }
  };
  api.session = (sessionURL, init) => send(googleURL(sessionURL), { method: "PUT", retry: false, timeout: 300000, ...init });
  return api;
}
async function optional(api, apiPath) {
  try {
    return await api(apiPath);
  } catch (e) {
    if (e instanceof APIError && e.status === 404) return null;
    throw e;
  }
}

export async function uploadBundle(api, editId, bytes, chunkSize = CHUNK) {
  check(chunkSize > 0 && chunkSize % (256 * 1024) === 0, "Upload chunks must be multiples of 256 KiB");
  const init = await api(`/edits/${editId}/bundles`, {
    method: "POST",
    upload: true,
    raw: true,
    query: { uploadType: "resumable" },
    headers: { "X-Upload-Content-Type": "application/octet-stream", "X-Upload-Content-Length": String(bytes.length) },
  });
  const session = init.headers.get("location");
  await init.body?.cancel();
  check(session, "Play did not return a resumable upload session");
  googleURL(session);
  let start = 0;
  let stalls = 0;
  for (;;) {
    const end = Math.min(start + chunkSize, bytes.length);
    const range = start < bytes.length ? `bytes ${start}-${end - 1}/${bytes.length}` : `bytes */${bytes.length}`;
    let response;
    try {
      response = await api.session(session, {
        body: bytes.subarray(start, end),
        headers: { "Content-Type": "application/octet-stream", "Content-Range": range },
      });
    } catch {
      throw new Error("Bundle transfer interrupted; session URL omitted; rerun to upload into a fresh edit");
    }
    if (response.ok) return response.json();
    if (response.status !== 308) throw await apiError(response);
    await response.body?.cancel();
    // Play acknowledges the persisted prefix, which can be shorter than the chunk sent.
    const acknowledged = /^bytes=0-(\d+)$/.exec(response.headers.get("range") ?? "");
    const next = acknowledged ? Number(acknowledged[1]) + 1 : 0;
    stalls = next > start ? 0 : stalls + 1;
    check(stalls < 3 && next <= bytes.length, "Play stopped accepting bundle bytes; rerun to upload into a fresh edit");
    start = next;
  }
}
function releaseNotes(input) {
  return [...input.listings].filter(([, l]) => l.fields.releaseNotes).map(([language, l]) => ({ language, text: l.fields.releaseNotes }));
}
async function readEdit(api, editId, options, input) {
  const edit = `/edits/${editId}`;
  const remote = {};
  if (options.parts.includes("bundle")) {
    remote.bundles = (await api(`${edit}/bundles`)).bundles ?? [];
    remote.track = (await optional(api, `${edit}/tracks/${encodeURIComponent(options.track)}`)) ?? { track: options.track, releases: [] };
  }
  if (options.parts.includes("listing")) {
    remote.listings = new Map();
    for (const locale of input.listings.keys())
      remote.listings.set(locale, await optional(api, `${edit}/listings/${encodeURIComponent(locale)}`));
  }
  if (options.parts.includes("images")) {
    remote.images = new Map();
    for (const g of input.images)
      remote.images.set(`${g.locale}/${g.type}`, (await api(`${edit}/listings/${encodeURIComponent(g.locale)}/${g.type}`)).images ?? []);
  }
  return remote;
}
const summary = (rows) =>
  !rows.length
    ? "missing_local_artifacts"
    : rows.every((r) => r.status === "verified")
      ? "verified"
      : rows.some((r) => r.status === "differs")
        ? "differs"
        : "missing_remote";
function compare(remote, options, input) {
  const components = {};
  if (remote.bundles) {
    const code = input.versionCode;
    const bundle = code ? remote.bundles.find((b) => String(b.versionCode) === code) : null;
    const release = code ? (remote.track.releases ?? []).find((r) => (r.versionCodes ?? []).map(String).includes(code)) : null;
    const bytes = bundle && input.bundle ? bundle.sha256 === input.bundle.sha256 : null;
    const placed =
      !!release &&
      release.status === options.status &&
      sameCodes(release.versionCodes, [code]) &&
      sameNotes(release.releaseNotes, releaseNotes(input)) &&
      (!options["release-name"] || release.name === options["release-name"]);
    components.bundle = {
      status:
        !code || !input.bundle
          ? "missing_local_artifacts"
          : !bundle
            ? "missing_remote"
            : !bytes
              ? "differs"
              : placed
                ? "verified"
                : "unverified_release",
      versionCode: code,
      remoteSha256: bundle?.sha256 ?? null,
      artifactBytesConfirmed: bytes === true,
      track: options.track,
      release: release
        ? {
            name: release.name ?? null,
            status: release.status,
            versionCodes: release.versionCodes,
            releaseNoteLanguages: (release.releaseNotes ?? []).map((n) => n.language),
          }
        : null,
    };
  }
  if (remote.listings) {
    const locales = [...input.listings]
      .filter(([, l]) => TEXT.some((k) => l.fields[k]))
      .map(([locale, l]) => {
        const current = remote.listings.get(locale);
        const differs = TEXT.filter((k) => l.fields[k] && clean(current?.[k]) !== clean(l.fields[k]));
        return { locale, status: !current ? "missing_remote" : differs.length ? "differs" : "verified", differs };
      });
    components.listing = { status: summary(locales), locales };
  }
  if (remote.images) {
    const groups = input.images.map((g) => {
      const have = remote.images.get(`${g.locale}/${g.type}`).map((x) => x.sha256);
      const want = g.items.map((x) => x.sha256);
      return {
        locale: g.locale,
        type: g.type,
        status: !have.length ? "missing_remote" : sameList(have, want) ? "verified" : "differs",
        expected: want.length,
        remote: have.length,
      };
    });
    components.images = { status: summary(groups), groups };
  }
  return components;
}
function requireVerified(components, message) {
  const failed = Object.entries(components).filter(([, c]) => c.status !== "verified");
  check(!failed.length, `${message}: ${failed.map(([name, c]) => `${name} ${c.status}`).join(", ")}`);
}

async function stage(api, editId, options, input, receipt, chunkSize) {
  const edit = `/edits/${editId}`;
  const before = await readEdit(api, editId, options, input);
  const code = input.versionCode;
  let releases = null;
  // Preflight every conflict before the first write.
  if (before.bundles) {
    const existing = before.bundles.find((b) => String(b.versionCode) === code);
    check(
      !existing || existing.sha256 === input.bundle.sha256,
      `versionCode ${code} already holds a different bundle on Play; build a new versionCode`,
    );
    if (compare({ bundles: before.bundles, track: before.track }, options, input).bundle.status !== "verified") {
      const current = before.track.releases ?? [];
      // Promoting this versionCode's draft is fine; demoting or reshaping a served release is not.
      const served = current.find(
        (r) => r.status !== "draft" && r.status !== options.status && (r.versionCodes ?? []).map(String).includes(code),
      );
      check(!served, `versionCode ${code} is already ${served?.status} on ${options.track}; a ${options.status} release would replace it`);
      const drafts = current.filter((r) => r.status === "draft" && !sameCodes(r.versionCodes, [code]));
      check(
        options.status !== "draft" || !drafts.length || options.replace,
        `Track ${options.track} already holds a draft with versionCodes ${drafts.map((r) => (r.versionCodes ?? []).join("+")).join(", ")}; --replace is required`,
      );
      const notes = releaseNotes(input);
      // The new release supersedes releases of the same status and any release already carrying this versionCode.
      releases = [
        ...current.filter((r) => r.status !== options.status && !(r.versionCodes ?? []).map(String).includes(code)),
        {
          ...(options["release-name"] ? { name: options["release-name"] } : {}),
          versionCodes: [code],
          status: options.status,
          ...(notes.length ? { releaseNotes: notes } : {}),
        },
      ];
    }
  }
  if (before.listings)
    for (const [locale, l] of input.listings)
      check(
        before.listings.get(locale) || l.fields.title || !TEXT.some((k) => l.fields[k]),
        `${locale} has no Play listing yet; its listing.md needs a Title`,
      );
  if (before.images)
    for (const g of input.images) {
      const want = new Set(g.items.map((x) => x.sha256));
      const foreign = before.images.get(`${g.locale}/${g.type}`).filter((x) => !want.has(x.sha256));
      check(
        !foreign.length || options.replace,
        `${g.locale} ${g.type} holds ${foreign.length} image(s) not in the manifest; --replace is required`,
      );
    }

  let changed = false;
  if (before.bundles) {
    if (before.bundles.some((b) => String(b.versionCode) === code))
      receipt.save("bundle_reused", { versionCode: code, sha256: input.bundle.sha256 });
    else {
      receipt.save("bundle_upload_intent", { versionCode: code, sha256: input.bundle.sha256, bytes: input.bundle.size });
      const bundle = await uploadBundle(api, editId, input.bundle.bytes, chunkSize);
      check(
        String(bundle.versionCode) === code,
        `Play read versionCode ${bundle.versionCode} from the AAB, not ${code}; nothing was committed`,
      );
      check(bundle.sha256 === input.bundle.sha256, "Play's bundle SHA-256 differs from the local AAB; nothing was committed");
      receipt.save("bundle_uploaded", { versionCode: code, sha256: bundle.sha256 });
      changed = true;
    }
    if (releases) {
      await api(`${edit}/tracks/${encodeURIComponent(options.track)}`, { method: "PUT", json: { track: options.track, releases } });
      receipt.save("track_staged", { track: options.track, status: options.status, versionCodes: [code] });
      changed = true;
    }
  }
  if (before.listings)
    for (const [locale, l] of input.listings) {
      const fields = Object.fromEntries(TEXT.filter((k) => l.fields[k]).map((k) => [k, l.fields[k]]));
      const current = before.listings.get(locale);
      if (!Object.keys(fields).length || (current && Object.entries(fields).every(([k, v]) => clean(current[k]) === clean(v)))) continue;
      const at = `${edit}/listings/${encodeURIComponent(locale)}`;
      // PATCH leaves the preview video and unlisted fields alone; a new locale needs PUT.
      if (current) await api(at, { method: "PATCH", json: fields });
      else await api(at, { method: "PUT", json: { language: locale, ...fields } });
      receipt.save("listing_staged", { locale, fields: Object.keys(fields) });
      changed = true;
    }
  if (before.images)
    for (const g of input.images) {
      const at = `${edit}/listings/${encodeURIComponent(g.locale)}/${g.type}`;
      const have = before.images.get(`${g.locale}/${g.type}`).map((x) => x.sha256);
      const want = g.items.map((x) => x.sha256);
      if (sameList(have, want)) continue;
      // Play has no reorder call: keep a matching prefix, otherwise clear the type and upload in order.
      const keep = have.length <= want.length && have.every((s, i) => s === want[i]) ? have.length : 0;
      if (!keep && have.length) {
        await api(at, { method: "DELETE" });
        receipt.save("images_cleared", { locale: g.locale, type: g.type, count: have.length });
      }
      for (const item of g.items.slice(keep)) {
        const bytes = fs.readFileSync(item.file);
        check(hash(bytes) === item.sha256, `Image changed during upload: ${path.basename(item.file)}`);
        const { image } = await api(at, {
          method: "POST",
          upload: true,
          query: { uploadType: "media" },
          body: bytes,
          headers: { "Content-Type": item.extension === ".png" ? "image/png" : "image/jpeg" },
          timeout: 300000,
        });
        check(image?.sha256 === item.sha256, `Play's ${g.type} SHA-256 differs from ${path.basename(item.file)}; nothing was committed`);
      }
      receipt.save("images_staged", { locale: g.locale, type: g.type, sha256: want });
      changed = true;
    }
  return changed;
}
async function openEdit(api, receipt) {
  const edit = await api("/edits", { method: "POST" });
  check(edit?.id, "Play did not return an edit ID");
  const expires = Number(edit.expiryTimeSeconds);
  receipt.save("edit_opened", { editId: edit.id, expiresAt: expires ? new Date(expires * 1000).toISOString() : null });
  return edit.id;
}
async function discard(api, editId) {
  try {
    await api(`/edits/${editId}`, { method: "DELETE" });
  } catch {
    /* an abandoned edit expires on its own */
  }
}
async function upload(api, options, input, receipt, deps) {
  const outcome = (status, extra) => ({
    status,
    target: { packageName: options.package },
    track: options.track,
    releaseStatus: options.status,
    requested: options.parts,
    ...extra,
  });
  let editId = await openEdit(api, receipt);
  try {
    const changed = await stage(api, editId, options, input, receipt, deps.chunkSize);
    await api(`/edits/${editId}:validate`, { method: "POST" });
    const staged = compare(await readEdit(api, editId, options, input), options, input);
    requireVerified(staged, "The staged edit does not match the requested change; nothing was committed");
    receipt.save("validated", { editId, changed, commit: !!options.commit });
    if (!changed) return outcome("verified", { committed: false, unchanged: true, components: staged });
    if (!options.commit)
      return outcome("validated", {
        overall: "incomplete",
        committed: false,
        components: staged,
        next: "The edit was validated and deleted. Rerun with --commit when the instruction covers the commit's effects.",
      });
    receipt.save("commit_intent", { editId });
    try {
      await api(`/edits/${editId}:commit`, {
        method: "POST",
        query: { changesInReviewBehavior: "ERROR_IF_IN_REVIEW" },
        retry: false,
        timeout: 300000,
      });
    } catch (e) {
      if (e instanceof APIError && e.reasons.includes("CHANGES_ALREADY_IN_REVIEW"))
        throw new Pending("Changes are already in review; nothing was committed. Wait for Google's decision, then rerun");
      if (e instanceof APIError && e.status < 500) throw e;
      // The edit may have committed: keep it for reconciliation instead of deleting it.
      const uncertain = editId;
      editId = null;
      receipt.save("commit_uncertain", { editId: uncertain });
      throw new Pending(`Commit outcome is unknown for edit ${uncertain}; run status and reconcile before retrying`);
    }
    const committed = editId;
    editId = null;
    if (options.parts.includes("bundle"))
      receipt.data.build = { versionCode: input.versionCode, sha256: input.bundle.sha256, track: options.track, status: options.status };
    receipt.save("committed", { editId: committed });
    editId = await openEdit(api, receipt);
    const components = compare(await readEdit(api, editId, options, input), options, input);
    requireVerified(components, `Edit ${committed} was committed but Play's readback differs; inspect Play Console before retrying`);
    const result = outcome("verified", {
      committed: true,
      editId: committed,
      components,
      next: "Commit is not review approval or availability. Read Publishing overview and record Google's state.",
    });
    receipt.save("readback_verified", result);
    return result;
  } finally {
    if (editId) await discard(api, editId);
  }
}
async function observe(api, options, input, receipt) {
  const editId = await openEdit(api, receipt);
  try {
    const components = compare(await readEdit(api, editId, options, input), options, input);
    for (const error of input.errors)
      for (const part of error.parts) if (components[part]) components[part].status = "invalid_local_artifacts";
    const tracks = ((await api(`/edits/${editId}/tracks`)).tracks ?? []).map((t) => ({
      track: t.track,
      releases: (t.releases ?? []).map((r) => ({
        name: r.name ?? null,
        status: r.status,
        versionCodes: r.versionCodes ?? [],
        ...(r.userFraction === undefined ? {} : { userFraction: r.userFraction }),
      })),
    }));
    const listingLocales = ((await api(`/edits/${editId}/listings`)).listings ?? []).map((l) => l.language);
    return {
      status: "observed",
      overall: Object.values(components).every((c) => c.status === "verified") ? "complete" : "incomplete",
      target: { packageName: options.package },
      track: options.track,
      releaseStatus: options.status,
      localErrors: input.errors,
      components,
      tracks,
      listingLocales,
    };
  } finally {
    await discard(api, editId);
  }
}
export async function run(options, deps = {}) {
  const input = loadInputs(options);
  if (options.command === "plan")
    return {
      status: "planned",
      overall: "incomplete",
      target: { packageName: options.package },
      manifestSha256: input.manifestSha256,
      track: options.track,
      releaseStatus: options.status,
      bundle: input.bundle ? { versionCode: input.versionCode, sha256: input.bundle.sha256, bytes: input.bundle.size } : null,
      listings: [...input.listings].map(([locale, l]) => ({
        locale,
        characters: Object.fromEntries(Object.entries(l.fields).map(([k, v]) => [k, chars(v)])),
      })),
      images: input.images.map((g) => ({ locale: g.locale, type: g.type, count: g.items.length })),
      remoteVerified: false,
    };
  if (options.command === "upload") requireInputs(options, input);
  const fetcher = deps.fetch ?? fetch;
  const api = createAPI(options.package, deps.token ?? serviceAccountToken(credentials(), fetcher), fetcher, deps.sleep ?? wait);
  const receipt = new Receipt(options.receipt, { packageName: options.package }, input.manifestSha256);
  try {
    if (options.command === "status") {
      const result = await observe(api, options, input, receipt);
      receipt.save("status_readback", result);
      return result;
    }
    return await upload(api, options, input, receipt, deps);
  } catch (e) {
    receipt.save(e instanceof Pending ? "pending_external" : "failed", { command: options.command });
    throw e;
  }
}
const HELP = `ShippyKit Google Play uploader (Node 18+, no dependencies)\n\nnode deploy/play-upload.mjs <plan|status|upload> \\\n  --release-output release-output --package com.example.app\n\nupload needs --parts with any of bundle,listing,images; they share one edit.\nOptional: --version-code N (defaults to android_bundle.version_code);\n--aab PATH --aab-sha256 HASH; --track internal (default; production is refused);\n--status draft|completed (default draft); --release-name NAME; --locales en-US,de-DE;\n--replace; --commit; --receipt PATH.\n\nplan: local manifest, copy-limit, image and AAB checks only.\nstatus: compares Play with the manifest in a read-only edit, then deletes it.\nupload: preflights conflicts, stages, validates and rereads the edit. Without --commit\nthe edit is deleted. --commit commits with changesInReviewBehavior=ERROR_IF_IN_REVIEW\nand reads the result back in a fresh edit. A commit can send the app's pending changes\nfor review. --replace allows replacing unmatched listing images or another draft release.\n\nService-account key: PLAY_SERVICE_ACCOUNT_KEY or GOOGLE_APPLICATION_CREDENTIALS\n(EMBER_PLAY_KEY fallback). Invite its email in Play Console Users and permissions.\nReceipt defaults to release-output/play-upload-receipt.json. Preserve it on retry.\nExit 0: verified/validated/planned/observed; exit 2: pending external; exit 1: failed.\nNever touches production, the preview video, app content forms or Send for review.\n`;
if (process.argv[1] && import.meta.url === pathToFileURL(path.resolve(process.argv[1])).href) {
  try {
    const options = parseArgs(process.argv.slice(2));
    if (options.help) process.stdout.write(HELP);
    else process.stdout.write(`${JSON.stringify(await run(options), null, 2)}\n`);
  } catch (e) {
    process.stderr.write(`${JSON.stringify({ status: e instanceof Pending ? "pending_external" : "failed", message: e.message })}\n`);
    process.exitCode = e instanceof Pending ? 2 : 1;
  }
}
