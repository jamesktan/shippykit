#!/usr/bin/env node
import { spawnSync } from "node:child_process";
import crypto from "node:crypto";
// Portable ShippyKit Apple draft uploader. Node 18+, no dependencies.
// Apple reference: /documentation/appstoreconnectapi/understanding-the-app-asset-library
// Scope: iOS screenshots and an already signed distribution IPA. Never review or release.
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { pathToFileURL } from "node:url";

const ORIGIN = "https://api.appstoreconnect.apple.com";
const READY = new Set(["PREPARE_FOR_SUBMISSION", "READY_FOR_REVIEW", "WAITING_FOR_REVIEW", "IN_REVIEW", "ACCEPTED", "APPROVED"]);
const PLACEMENT_READY = new Set([
  "ACTIVE",
  "PARENT_PREPARE_FOR_SUBMISSION",
  "PARENT_READY_FOR_REVIEW",
  "PARENT_WAITING_FOR_REVIEW",
  "PARENT_IN_REVIEW",
  "PARENT_APPROVED",
]);
const EDITABLE = new Set(["PREPARE_FOR_SUBMISSION", "DEVELOPER_REJECTED", "REJECTED", "METADATA_REJECTED", "INVALID_BINARY"]);
const hash = (bytes, algorithm = "sha256") => crypto.createHash(algorithm).update(bytes).digest("hex");
const attrs = (resource) => resource?.attributes ?? {};
const list = (doc) => (Array.isArray(doc?.data) ? doc.data : doc?.data ? [doc.data] : []);
const rel = (resource, name) => resource?.relationships?.[name]?.data?.id;
const qs = (values) => `?${new URLSearchParams(values).toString()}`;
const body = (type, attributes = {}, relationships = {}, id) => ({
  data: {
    type,
    ...(id ? { id } : {}),
    attributes,
    ...(Object.keys(relationships).length
      ? { relationships: Object.fromEntries(Object.entries(relationships).map(([k, v]) => [k, { data: v }])) }
      : {}),
  },
});
const link = (type, id) => ({ type, id });
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
  constructor(status, codes) {
    super(`Apple HTTP ${status}: ${codes.join(", ") || "request failed"}`);
    this.status = status;
  }
}

export function parseArgs(argv) {
  const command = argv.shift();
  if (!command || command === "--help" || command === "help") return { help: true };
  check(["plan", "status", "screenshots", "build"].includes(command), "Expected plan, status, screenshots, or build");
  const values = { command };
  const flags = new Set(["replace", "associate"]);
  const names = new Set([
    "release-output",
    "app-id",
    "bundle-id",
    "version",
    "binary-version",
    "build-number",
    "receipt",
    "timeout-seconds",
    "poll-seconds",
    "media-mode",
    "ipa",
    "ipa-sha256",
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
  for (const name of ["app-id", "bundle-id", "version", "build-number"]) check(values[name], `Required --${name}`);
  check(/^\d+$/.test(values["app-id"]), "App ID must be numeric");
  check(/^[A-Za-z0-9.-]+$/.test(values["bundle-id"]), "Invalid bundle ID");
  for (const name of ["version", "binary-version", "build-number"])
    if (values[name]) check(/^\d+(?:\.\d+){0,2}$/.test(values[name]), `Invalid ${name}`);
  values["binary-version"] ??= values.version;
  values["release-output"] = path.resolve(values["release-output"] ?? "release-output");
  values.receipt = path.resolve(values.receipt ?? path.join(values["release-output"], "apple-upload-receipt.json"));
  values["media-mode"] ??= "auto";
  check(["auto", "modern", "legacy"].includes(values["media-mode"]), "Invalid media mode");
  for (const [name, fallback] of [
    ["timeout-seconds", 600],
    ["poll-seconds", 10],
  ]) {
    values[name] = Number(values[name] ?? fallback);
    check(Number.isFinite(values[name]) && values[name] > 0, `Invalid ${name}`);
  }
  return values;
}

export function noSymlink(filename) {
  let cursor = path.parse(path.resolve(filename)).root;
  for (const part of path.resolve(filename).slice(cursor.length).split(path.sep)) {
    cursor = path.join(cursor, part);
    if (fs.existsSync(cursor) && fs.lstatSync(cursor).isSymbolicLink()) {
      const systemAlias =
        process.platform === "darwin" && ["/tmp", "/var", "/etc"].includes(cursor) && fs.realpathSync(cursor) === `/private${cursor}`;
      check(systemAlias, `Symlink is not permitted: ${path.basename(cursor)}`);
    }
  }
}
export function sourceFile(root, relative) {
  check(
    typeof relative === "string" && relative && !relative.includes("\\") && !path.isAbsolute(relative),
    "Expected a relative manifest path",
  );
  check(!relative.split("/").some((part) => part === ".." || part === "." || !part), "Unsafe manifest path");
  const filename = path.resolve(root, relative);
  noSymlink(filename);
  check(fs.statSync(filename).isFile(), "Manifest source must be a regular file");
  return filename;
}
export function imageInfo(bytes) {
  if (bytes.length >= 33 && bytes.subarray(0, 8).equals(Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]))) {
    let offset = 8;
    let transparent = [4, 6].includes(bytes[25]);
    while (offset + 12 <= bytes.length) {
      const length = bytes.readUInt32BE(offset);
      const tag = bytes.toString("ascii", offset + 4, offset + 8);
      check(offset + 12 + length <= bytes.length, "Truncated PNG");
      if (tag === "tRNS") transparent = true;
      offset += length + 12;
      if (tag === "IEND") break;
    }
    return { width: bytes.readUInt32BE(16), height: bytes.readUInt32BE(20), extension: ".png", alpha: transparent };
  }
  if (bytes[0] === 255 && bytes[1] === 216) {
    let p = 2;
    while (p + 4 < bytes.length) {
      if (bytes[p++] !== 255) continue;
      let marker = bytes[p++];
      while (marker === 255) marker = bytes[p++];
      if (marker === 217 || marker === 218) break;
      const length = bytes.readUInt16BE(p);
      check(length >= 2 && p + length <= bytes.length, "Truncated JPEG");
      if ([192, 193, 194, 195, 197, 198, 199, 201, 202, 203, 205, 206, 207].includes(marker))
        return { width: bytes.readUInt16BE(p + 5), height: bytes.readUInt16BE(p + 3), extension: ".jpg", alpha: false };
      p += length;
    }
  }
  throw new Error("Screenshot must be a readable PNG or JPEG");
}
export function loadManifest(options) {
  const root = options["release-output"];
  const filename = sourceFile(root, "manifest.json");
  const raw = fs.readFileSync(filename);
  const manifest = JSON.parse(raw);
  const entries = manifest.files ?? manifest.artifacts;
  check(Array.isArray(entries), "Manifest needs a files or artifacts array");
  check(!manifest.bundle_identifier || manifest.bundle_identifier === options["bundle-id"], "Manifest bundle ID differs from target");
  const seen = new Set();
  const screenshots = [];
  const screenshotEntries = entries.filter(
    (item) =>
      (item.kind === "app_store_screenshot" || item.kind === "store-screenshot") &&
      item.platform !== "android" &&
      !item.path?.startsWith("stores/android/"),
  );
  const screenshotErrors = [];
  for (const item of options.command === "build" ? [] : screenshotEntries) {
    try {
      /* validate only the selected media branch */
      check(!seen.has(item.path), "Duplicate screenshot path");
      seen.add(item.path);
      check(!/(^|\/)(captures|builds|logs|profiles|private)(\/|$)/i.test(item.path), "Screenshot must be a curated store artifact");
      const file = sourceFile(root, item.path);
      const bytes = fs.readFileSync(file);
      check(/^[a-f0-9]{64}$/.test(item.sha256 ?? "") && hash(bytes) === item.sha256, `Screenshot hash mismatch: ${item.path}`);
      check(item.bytes === undefined || item.bytes === bytes.length, "Screenshot byte count mismatch");
      const info = imageInfo(bytes);
      check(!info.alpha, "App Store screenshots must be opaque");
      if (item.media?.width)
        check(item.media.width === info.width && item.media.height === info.height, "Screenshot dimensions disagree with manifest");
      const locale = item.locale ?? /^stores\/ios\/([^/]+)\//.exec(item.path)?.[1] ?? manifest.locale;
      check(typeof locale === "string" && /^[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*$/.test(locale), "Screenshot locale is missing or invalid");
      screenshots.push({
        file,
        sha256: item.sha256,
        size: bytes.length,
        locale,
        ...info,
        group: item.asc_placement_group,
        legacyDisplay: item.asc_display_type,
        order: item.order ?? item.storeOrder ?? screenshots.length,
      });
    } catch (error) {
      if (options.command !== "status") throw error;
      screenshotErrors.push({ path: item.path, reason: "local_asset_validation_failed" });
    }
  }
  screenshots.sort((a, b) => a.order - b.order);
  const distribution = manifest.distribution_build;
  const ipa = options.ipa ? path.resolve(options.ipa) : distribution?.path ? path.resolve(root, distribution.path) : null;
  if (!options.ipa && distribution?.path)
    check(!path.isAbsolute(distribution.path) && !distribution.path.split(/[\\/]/).includes(".."), "Unsafe distribution IPA path");
  const ipaHash = options["ipa-sha256"] ?? distribution?.sha256;
  return {
    manifest,
    screenshotErrors,
    screenshotEntryCount: screenshotEntries.length,
    manifestSha256: hash(raw),
    screenshots,
    ipa,
    ipaHash,
    previewCount: entries.filter((x) => x.kind === "app_store_preview").length,
  };
}

export function credentials(env = process.env) {
  const keyId = env.ASC_KEY_ID || env.EMBER_ASC_KEY_ID;
  const issuer = env.ASC_ISSUER_ID || env.EMBER_ASC_ISSUER_ID;
  check(keyId && /^[A-Za-z0-9]+$/.test(keyId) && issuer, "Team API key references ASC_KEY_ID and ASC_ISSUER_ID are required");
  return {
    keyId,
    issuer,
    keyPath: env.ASC_KEY_PATH || env.EMBER_ASC_KEY_PATH || path.join(os.homedir(), ".appstoreconnect/private_keys", `AuthKey_${keyId}.p8`),
  };
}
export function createAPI(auth, fetcher = fetch) {
  return async (apiPath, method = "GET", payload) => {
    const url = new URL(apiPath, ORIGIN);
    check(url.origin === ORIGIN && /^\/v[12]\//.test(url.pathname) && !url.username && !url.password, "Refusing non-Apple API URL");
    const encode = (x) => Buffer.from(JSON.stringify(x)).toString("base64url");
    const now = Math.floor(Date.now() / 1000);
    const input = `${encode({ alg: "ES256", kid: auth.keyId, typ: "JWT" })}.${encode({ iss: auth.issuer, iat: now, exp: now + 600, aud: "appstoreconnect-v1" })}`;
    const token = `${input}.${crypto.sign("sha256", Buffer.from(input), { key: fs.readFileSync(auth.keyPath), dsaEncoding: "ieee-p1363" }).toString("base64url")}`;
    const response = await fetcher(url, {
      method,
      headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
      body: payload === undefined ? undefined : JSON.stringify(payload),
      redirect: "error",
      signal: AbortSignal.timeout(30000),
    });
    const text = await response.text();
    let doc;
    try {
      doc = text ? JSON.parse(text) : {};
    } catch {
      throw new Error(`Apple HTTP ${response.status}: invalid JSON response`);
    }
    if (!response.ok)
      throw new APIError(
        response.status,
        (doc.errors ?? []).map((e) => String(e.code ?? e.title ?? "error")),
      );
    return doc;
  };
}
export async function all(api, apiPath) {
  const data = [];
  const included = [];
  const seen = new Set();
  while (apiPath) {
    check(!seen.has(apiPath) && seen.size < 1000, "Invalid Apple pagination");
    seen.add(apiPath);
    const doc = await api(apiPath);
    data.push(...list(doc));
    included.push(...(doc.included ?? []));
    apiPath = doc.links?.next;
  }
  return { data, included };
}
async function optional(api, apiPath) {
  try {
    return await api(apiPath);
  } catch (e) {
    if (e instanceof APIError && e.status === 404) return { data: null };
    throw e;
  }
}
export async function target(api, options) {
  const app = (await api(`/v1/apps/${options["app-id"]}`)).data;
  check(attrs(app).bundleId === options["bundle-id"], "Remote app bundle ID does not match target");
  const versions = list(await all(api, `/v1/apps/${app.id}/appStoreVersions${qs({ "filter[platform]": "IOS", limit: "200" })}`));
  const matches = versions.filter((v) => attrs(v).versionString === options.version && attrs(v).platform === "IOS");
  check(matches.length === 1, `Expected exactly one iOS draft version ${options.version}; create/select it explicitly`);
  return {
    app,
    version: matches[0],
    localizations: list(await all(api, `/v1/appStoreVersions/${matches[0].id}/appStoreVersionLocalizations?limit=200`)),
  };
}
export function screenshotGroups(refdata, screenshots) {
  const a = attrs(list(refdata)[0]);
  const feature = (a.features ?? []).find((x) => x.featureId === "APP_STORE_VERSIONS");
  const policy = feature?.placementPolicies?.find((x) => x.placementType === "APP_SCREENSHOT");
  const type = (a.placementTypes ?? []).find((x) => x.placementTypeId === "APP_SCREENSHOT");
  check(policy && type?.acceptsAssetCategories?.includes("APP_SCREENSHOTS_AND_PREVIEWS"), "Unrecognized Apple screenshot reference data");
  const groups = new Map();
  for (const item of screenshots) {
    const specs = (a.imageSpecs ?? [])
      .filter((s) => {
        const d = s.dimensions ?? {};
        return (
          item.width >= d.minWidth &&
          item.width <= d.maxWidth &&
          item.height >= d.minHeight &&
          item.height <= d.maxHeight &&
          s.fileExtensions?.includes(item.extension) &&
          item.size <= s.maxFileSize &&
          (!item.alpha || s.alphaAllowed)
        );
      })
      .map((s) => s.specId);
    const candidates = (type.specMappings ?? []).filter(
      (m) =>
        m.specs?.some((id) => specs.includes(id)) &&
        (a.placementProfileGroups ?? []).some(
          (g) => g.placementProfileGroupId === m.placementGroupId && ["IPHONE_APP_STORE", "IPAD_APP_STORE"].includes(g.platform),
        ) &&
        (!item.group || item.group === m.placementGroupId),
    );
    check(
      candidates.length === 1,
      `Screenshot ${item.width}x${item.height} has ${candidates.length} eligible groups; specify manifest asc_placement_group if ambiguous`,
    );
    const mapping = candidates[0];
    const limit = policy.groupLimits?.find((x) => x.groupIds?.includes(mapping.placementGroupId));
    check(limit, "Screenshot group unavailable for App Store versions");
    const key = `${item.locale}/${mapping.placementGroupId}`;
    if (!groups.has(key))
      groups.set(key, { locale: item.locale, group: mapping.placementGroupId, specIds: mapping.specs, max: limit.maxCount, items: [] });
    groups.get(key).items.push(item);
  }
  for (const group of groups.values()) check(group.items.length <= group.max, `Too many screenshots for ${group.group}`);
  return [...groups.values()];
}

function targetIdentity(o) {
  return {
    appId: o["app-id"],
    bundleId: o["bundle-id"],
    version: o.version,
    binaryVersion: o["binary-version"],
    buildNumber: o["build-number"],
  };
}
export class Receipt {
  constructor(filename, identity, manifestSha256) {
    this.filename = filename;
    noSymlink(filename);
    this.data = fs.existsSync(filename)
      ? JSON.parse(fs.readFileSync(filename, "utf8"))
      : { schemaVersion: 1, target: identity, events: [], build: null };
    check(
      this.data.schemaVersion === 1 && JSON.stringify(this.data.target) === JSON.stringify(identity),
      "Receipt belongs to another target; use a new receipt path",
    );
    this.data.manifestSha256 = manifestSha256;
  }
  save(event, detail = {}) {
    this.data.updatedAt = new Date().toISOString();
    this.data.events.push({ at: this.data.updatedAt, event, ...detail });
    noSymlink(this.filename);
    fs.mkdirSync(path.dirname(this.filename), { recursive: true });
    const tmp = `${this.filename}.${crypto.randomBytes(6).toString("hex")}.tmp`;
    try {
      const fd = fs.openSync(tmp, "wx", 0o600);
      try {
        fs.writeFileSync(fd, `${JSON.stringify(this.data, null, 2)}\n`);
        fs.fsyncSync(fd);
      } finally {
        fs.closeSync(fd);
      }
      fs.renameSync(tmp, this.filename);
    } finally {
      if (fs.existsSync(tmp)) fs.unlinkSync(tmp);
    }
  }
}
export async function placements(api, localizationId, group) {
  const query = { "filter[placementType]": "APP_SCREENSHOT", include: "image", sort: "placementGroupPosition", limit: "200" };
  if (group) query["filter[placementGroup]"] = group;
  const doc = await all(api, `/v1/appStoreVersionLocalizations/${localizationId}/placements${qs(query)}`);
  const images = new Map(doc.included.map((x) => [x.id, x]));
  const result = [];
  for (const placement of doc.data) {
    const imageId = rel(placement, "image");
    const image = images.get(imageId) ?? (imageId ? (await api(`/v1/appAssetLibraryImages/${imageId}`)).data : null);
    result.push({ placement, image });
  }
  return result; // Apple provides order in the sequence, NOT an attribute.
}
const screenshotEvidence = (rows) =>
  rows.map(({ placement, image }) => ({
    placementId: placement.id,
    imageId: image?.id,
    group: attrs(placement).placementGroup,
    placementState: attrs(placement).state,
    fileName: attrs(image).fileName,
    state: attrs(image).state,
    specId: attrs(image).specId,
  }));
function matches(rows, group) {
  return (
    rows.length === group.items.length &&
    rows.every(
      (row, i) =>
        attrs(row.image).fileName === group.items[i].sha256 + group.items[i].extension &&
        READY.has(attrs(row.image).state) &&
        group.specIds.includes(attrs(row.image).specId) &&
        PLACEMENT_READY.has(attrs(row.placement).state),
    )
  );
}
export function screenshotOrdering(peers, ids) {
  check(
    peers.filter((p) => attrs(p).placementType === "APP_SCREENSHOT").every((p) => ids.includes(p.id)),
    "Screenshot placements changed concurrently; reconcile before ordering",
  );
  return [...ids];
}
async function poll(read, accept, options, sleep, label) {
  const end = Date.now() + options["timeout-seconds"] * 1000;
  for (;;) {
    const value = await read();
    if (accept(value)) return value;
    if (Date.now() >= end) throw new Pending(`${label} still pending; resume with the same receipt`);
    await sleep(options["poll-seconds"] * 1000);
  }
}
export async function uploadParts(resource, bytes, fetcher) {
  const ops = attrs(resource).uploadOperations;
  check(Array.isArray(ops) && ops.length, "Reservation did not include upload operations");
  const intervals = ops.map((op) => [op.offset, op.offset + op.length]).sort((a, b) => a[0] - b[0]);
  check(
    intervals[0][0] === 0 &&
      intervals.every(
        ([start, end], i) =>
          Number.isSafeInteger(start) &&
          Number.isSafeInteger(end) &&
          end > start &&
          end <= bytes.length &&
          (!i || intervals[i - 1][1] === start),
      ) &&
      intervals.at(-1)[1] === bytes.length,
    "Upload ranges do not cover the asset exactly",
  );
  for (const op of ops) {
    const url = new URL(op.url);
    check(url.protocol === "https:" && !url.username && !url.password && op.method === "PUT", "Unsafe upload operation");
    const headers = Object.fromEntries(
      (op.requestHeaders ?? []).map((h) => {
        check(!/^(authorization|cookie|proxy-authorization)$/i.test(h.name), "Unexpected credential header in upload operation");
        return [h.name, h.value];
      }),
    );
    let response;
    try {
      response = await fetcher(url, {
        method: "PUT",
        headers,
        body: bytes.subarray(op.offset, op.offset + op.length),
        redirect: "error",
        signal: AbortSignal.timeout(120000),
      });
    } catch {
      throw new Pending("Asset transfer interrupted; signed URL omitted; resume with the same receipt");
    }
    if (!response.ok) throw new Error(`Asset transfer HTTP ${response.status}; signed URL omitted`);
  }
}
async function localize(api, t, locale, receipt) {
  let loc = t.localizations.find((l) => attrs(l).locale === locale);
  if (!loc) {
    receipt.save("localization_create_intent", { locale });
    loc = (
      await api(
        "/v1/appStoreVersionLocalizations",
        "POST",
        body("appStoreVersionLocalizations", { locale }, { appStoreVersion: link("appStoreVersions", t.version.id) }),
      )
    ).data;
    check(loc?.id, "Missing localization ID");
    t.localizations.push(loc);
    receipt.save("localization_created", { locale, id: loc.id });
  }
  return loc;
}
async function modernScreenshots(api, t, library, groups, options, receipt, fetcher, sleep) {
  const index = list(await all(api, `/v1/appAssetLibraries/${library.id}/images?limit=200`));
  const results = [];
  // Preflight all existing placements before any mutation.
  for (const group of groups) {
    const loc = t.localizations.find((x) => attrs(x).locale === group.locale);
    const rows = loc ? await placements(api, loc.id, group.group) : [];
    if (rows.some((r) => !group.items.some((i) => attrs(r.image).fileName === i.sha256 + i.extension)))
      check(options.replace, `Existing screenshots conflict in ${group.locale}/${group.group}; --replace is required`);
  }
  for (const group of groups) {
    const loc = await localize(api, t, group.locale, receipt);
    let rows = await placements(api, loc.id, group.group);
    if (matches(rows, group)) {
      results.push({ locale: group.locale, group: group.group, assets: screenshotEvidence(rows) });
      continue;
    }
    const desired = [];
    for (const item of group.items) {
      const name = item.sha256 + item.extension;
      let asset = index.find((x) => attrs(x).fileName === name && !["FAILED", "REJECTED", "ARCHIVED"].includes(attrs(x).state));
      if (!asset) {
        receipt.save("image_reservation_intent", { sha256: item.sha256, locale: group.locale, group: group.group });
        asset = (
          await api(
            "/v1/appAssetLibraryImages",
            "POST",
            body(
              "appAssetLibraryImages",
              {
                fileName: name,
                fileSize: item.size,
                category: "APP_SCREENSHOTS_AND_PREVIEWS",
                referenceName: `ShippyKit ${item.sha256.slice(0, 12)}`,
              },
              { assetLibrary: link("appAssetLibraries", library.id) },
            ),
          )
        ).data;
        check(asset?.id, "Missing image reservation ID");
        index.push(asset);
        receipt.save("image_reserved", { sha256: item.sha256, id: asset.id });
      }
      if (attrs(asset).state === "AWAITING_UPLOAD") {
        asset = (await api(`/v1/appAssetLibraryImages/${asset.id}`)).data;
        if (attrs(asset).state === "AWAITING_UPLOAD") {
          const bytes = fs.readFileSync(item.file);
          check(hash(bytes) === item.sha256, "Screenshot changed during upload");
          await uploadParts(asset, bytes, fetcher);
          await api(`/v1/appAssetLibraryImages/${asset.id}`, "PATCH", body("appAssetLibraryImages", { uploaded: true }, {}, asset.id));
          receipt.save("image_committed", { sha256: item.sha256, id: asset.id });
        }
      }
      asset = await poll(
        async () => {
          const a = (await api(`/v1/appAssetLibraryImages/${asset.id}`)).data;
          check(!["FAILED", "REJECTED", "ARCHIVED"].includes(attrs(a).state), `Image ${asset.id} processing failed: ${attrs(a).state}`);
          return a;
        },
        (a) => READY.has(attrs(a).state),
        options,
        sleep,
        `Image ${asset.id}`,
      );
      check(group.specIds.includes(attrs(asset).specId), "Processed image specification does not match selected group");
      desired.push(asset);
    }
    // New assets are processed before old placements are removed. Keep matching placements on resume.
    const ids = [];
    const used = new Set();
    for (const asset of desired) {
      const existing = rows.find((row) => row.image?.id === asset.id && !used.has(row.placement.id));
      if (existing) {
        ids.push(existing.placement.id);
        used.add(existing.placement.id);
      } else ids.push(null);
    }
    for (const row of rows.filter((r) => !used.has(r.placement.id))) {
      receipt.save("placement_delete_intent", { id: row.placement.id, locale: group.locale, group: group.group });
      await api(`/v1/appAssetLibraryPlacements/${row.placement.id}`, "DELETE");
    }
    for (let i = 0; i < desired.length; i++)
      if (!ids[i]) {
        receipt.save("placement_create_intent", { imageId: desired[i].id, locale: group.locale, group: group.group });
        const p = (
          await api(
            "/v1/appAssetLibraryPlacements",
            "POST",
            body(
              "appAssetLibraryPlacements",
              { placementType: "APP_SCREENSHOT", placementGroup: group.group },
              {
                image: link("appAssetLibraryImages", desired[i].id),
                appStoreVersionLocalization: link("appStoreVersionLocalizations", loc.id),
              },
            ),
          )
        ).data;
        check(p?.id, "Missing placement ID");
        ids[i] = p.id;
        receipt.save("placement_created", { id: p.id, imageId: desired[i].id });
      }
    // Apple orders each placement type on its own and refuses a request that mixes screenshots
    // with previews (409 ENTITY_ERROR.RELATIONSHIP.INVALID, seen 2026-10-28/29). Previews keep their positions.
    const peers = list(
      await all(
        api,
        `/v1/appStoreVersionLocalizations/${loc.id}/placements${qs({ "filter[placementGroup]": group.group, sort: "placementGroupPosition", limit: "200" })}`,
      ),
    );
    const ordered = screenshotOrdering(peers, ids);
    await api(
      "/v1/appAssetLibraryPlacementOrderingRequests",
      "POST",
      body(
        "appAssetLibraryPlacementOrderingRequests",
        { placementGroup: group.group },
        {
          orderedPlacements: ordered.map((id) => link("appAssetLibraryPlacements", id)),
          appStoreVersionLocalization: link("appStoreVersionLocalizations", loc.id),
        },
      ),
    );
    rows = await poll(
      () => placements(api, loc.id, group.group),
      (r) => matches(r, group),
      options,
      sleep,
      `Screenshot placement readback ${group.group}`,
    );
    const result = { locale: group.locale, group: group.group, assets: screenshotEvidence(rows) };
    results.push(result);
    receipt.save("screenshots_verified", result);
  }
  return {
    status: "verified",
    scope: "requested_screenshots",
    mode: "modern",
    groups: results,
    checksumEvidence: "local SHA-256 and remote digest filename; Apple does not return an image SHA-256",
  };
}

async function legacyScreenshots(api, t, items, options, receipt, fetcher, sleep) {
  // Compatibility is opt-in, never inferred from empty legacy sets.
  for (const loc of t.localizations) {
    const modern = await optional(api, `/v1/appStoreVersionLocalizations/${loc.id}/placements?limit=200`);
    check(!list(modern).length, "Modern placements exist; refusing legacy compatibility writes");
  }
  const groups = new Map();
  for (const item of items) {
    check(/^APP_[A-Z0-9_]+$/.test(item.legacyDisplay ?? ""), "Legacy mode requires explicit asc_display_type on every manifest screenshot");
    const key = `${item.locale}/${item.legacyDisplay}`;
    if (!groups.has(key)) groups.set(key, { locale: item.locale, display: item.legacyDisplay, items: [] });
    groups.get(key).items.push(item);
  }
  const results = [];
  for (const group of groups.values()) {
    check(group.items.length <= 10, "Legacy screenshot sets hold at most 10 screenshots");
    const loc = await localize(api, t, group.locale, receipt);
    let set = list(await all(api, `/v1/appStoreVersionLocalizations/${loc.id}/appScreenshotSets?limit=200`)).find(
      (x) => attrs(x).screenshotDisplayType === group.display,
    );
    if (!set) {
      receipt.save("legacy_set_create_intent", { locale: group.locale, display: group.display });
      set = (
        await api(
          "/v1/appScreenshotSets",
          "POST",
          body(
            "appScreenshotSets",
            { screenshotDisplayType: group.display },
            { appStoreVersionLocalization: link("appStoreVersionLocalizations", loc.id) },
          ),
        )
      ).data;
    }
    let existing = list(await all(api, `/v1/appScreenshotSets/${set.id}/appScreenshots?limit=200`));
    const unwanted = existing.filter((x) => !group.items.some((i) => attrs(x).fileName === i.sha256 + i.extension));
    check(!unwanted.length || options.replace, "Existing legacy screenshots conflict; --replace required");
    check(
      existing.length + group.items.filter((i) => !existing.some((x) => attrs(x).fileName === i.sha256 + i.extension)).length <= 10,
      "Legacy set has no safe staging capacity; use modern Asset Library or explicitly clean it up first",
    );
    const ids = [];
    for (const item of group.items) {
      let asset = existing.find((x) => attrs(x).fileName === item.sha256 + item.extension);
      const bytes = fs.readFileSync(item.file);
      check(hash(bytes) === item.sha256, "Screenshot changed during upload");
      if (!asset) {
        receipt.save("legacy_image_reservation_intent", { sha256: item.sha256 });
        asset = (
          await api(
            "/v1/appScreenshots",
            "POST",
            body(
              "appScreenshots",
              { fileName: item.sha256 + item.extension, fileSize: item.size },
              { appScreenshotSet: link("appScreenshotSets", set.id) },
            ),
          )
        ).data;
        receipt.save("legacy_image_reserved", { id: asset.id, sha256: item.sha256 });
      }
      asset = (await api(`/v1/appScreenshots/${asset.id}`)).data;
      if (attrs(asset).assetDeliveryState?.state === "AWAITING_UPLOAD") {
        await uploadParts(asset, bytes, fetcher);
        await api(
          `/v1/appScreenshots/${asset.id}`,
          "PATCH",
          body("appScreenshots", { uploaded: true, sourceFileChecksum: hash(bytes, "md5") }, {}, asset.id),
        );
      }
      await poll(
        async () => {
          const a = (await api(`/v1/appScreenshots/${asset.id}`)).data;
          check(attrs(a).assetDeliveryState?.state !== "FAILED", `Legacy screenshot ${asset.id} processing failed`);
          return a;
        },
        (a) => attrs(a).assetDeliveryState?.state === "COMPLETE",
        options,
        sleep,
        "Legacy screenshot",
      );
      ids.push(asset.id);
    }
    for (const asset of existing.filter((x) => !ids.includes(x.id))) {
      receipt.save("legacy_image_delete_intent", { id: asset.id });
      await api(`/v1/appScreenshots/${asset.id}`, "DELETE");
    }
    await api(`/v1/appScreenshotSets/${set.id}/relationships/appScreenshots`, "PATCH", {
      data: ids.map((id) => link("appScreenshots", id)),
    });
    existing = await poll(
      () => all(api, `/v1/appScreenshotSets/${set.id}/appScreenshots?limit=200`).then(list),
      (rows) =>
        rows.length === ids.length &&
        rows.every(
          (x, i) =>
            x.id === ids[i] &&
            attrs(x).assetDeliveryState?.state === "COMPLETE" &&
            attrs(x).fileName === group.items[i].sha256 + group.items[i].extension,
        ),
      options,
      sleep,
      "Legacy screenshot ordering",
    );
    const result = {
      locale: group.locale,
      display: group.display,
      ids: existing.map((x) => x.id),
      sha256: group.items.map((x) => x.sha256),
    };
    results.push(result);
    receipt.save("legacy_screenshots_verified", result);
  }
  return { status: "verified", scope: "requested_screenshots", mode: "legacy_compatibility", groups: results };
}

export async function findBuild(api, options) {
  const doc = await all(
    api,
    `/v1/builds${qs({ "filter[app]": options["app-id"], "filter[version]": options["build-number"], include: "preReleaseVersion", limit: "200" })}`,
  );
  const included = new Map(doc.included.map((x) => [x.id, x]));
  const found = [];
  for (const b of doc.data) {
    if (attrs(b).version !== options["build-number"]) continue;
    const p = included.get(rel(b, "preReleaseVersion")) ?? (await api(`/v1/builds/${b.id}/preReleaseVersion`)).data;
    if (attrs(p).version === options["binary-version"] && attrs(p).platform === "IOS") found.push(b);
  }
  check(found.length <= 1, "Multiple builds matched exact app/version/build");
  return found[0] ?? null;
}
export function nativeExec(command, args, extra = {}) {
  const r = spawnSync(command, args, { encoding: "utf8", maxBuffer: 8 * 1024 * 1024, timeout: 120000, ...extra });
  if (r.error || r.status !== 0)
    throw new Error(
      `Native command ${path.basename(command)} failed (${r.error?.code ?? r.status}); inspect the tool locally; output omitted from receipt`,
    );
  return r.stdout;
}
function entitlementAllowed(value, permission) {
  if (typeof value === "string" && typeof permission === "string") {
    const pattern = permission
      .split("*")
      .map((part) => part.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"))
      .join(".*");
    return new RegExp(`^${pattern}$`).test(value);
  }
  if (Array.isArray(value))
    return value.every((v) =>
      Array.isArray(permission)
        ? permission.some((p) => entitlementAllowed(v, p))
        : typeof permission === "string" && entitlementAllowed(v, permission),
    );
  if (value && typeof value === "object")
    return (
      permission && typeof permission === "object" && Object.entries(value).every(([key, v]) => entitlementAllowed(v, permission[key]))
    );
  return value === permission || (value === false && permission === true);
}
export function verifyIPA(filename, expectedHash, options, exec = nativeExec) {
  check(filename && /^[a-f0-9]{64}$/.test(expectedHash ?? ""), "A distribution IPA and SHA-256 are required");
  noSymlink(filename);
  const bytes = fs.readFileSync(filename);
  check(hash(bytes) === expectedHash, "Distribution IPA hash mismatch");
  const entries = exec("/usr/bin/unzip", ["-Z1", filename]).trim().split("\n");
  check(
    entries.every((x) => !x.startsWith("/") && !x.includes("\\") && !x.split("/").includes("..")),
    "Unsafe IPA archive paths",
  );
  const listing = exec("/usr/bin/unzip", ["-Z", "-l", filename]);
  check(!listing.split("\n").some((line) => /^l[rwx-]{9}\s/.test(line)), "IPA symlink entries are unsupported by this verifier");
  const apps = entries.filter((x) => /^Payload\/[^/]+\.app\/Info\.plist$/.test(x));
  check(apps.length === 1, "Expected one main iOS app in IPA");
  const plist = exec("/usr/bin/unzip", ["-p", filename, apps[0]], { encoding: "buffer" });
  const info = JSON.parse(exec("/usr/bin/plutil", ["-convert", "json", "-o", "-", "--", "-"], { input: plist }));
  check(
    info.CFBundleIdentifier === options["bundle-id"] &&
      String(info.CFBundleShortVersionString) === options["binary-version"] &&
      String(info.CFBundleVersion) === options["build-number"],
    "IPA bundle/version/build differs from explicit target",
  );
  check(info.CFBundleSupportedPlatforms?.includes("iPhoneOS"), "IPA is not an iPhoneOS distribution");
  const temp = fs.mkdtempSync(path.join(os.tmpdir(), "shippykit-ipa-"));
  const verifiedBundles = [];
  try {
    exec("/usr/bin/unzip", ["-q", filename, "-d", temp]);
    for (const entry of entries.filter((x) => /^Payload\//.test(x) && /\.(app|appex)\/Info\.plist$/.test(x))) {
      const app = path.join(temp, path.dirname(entry));
      exec("/usr/bin/codesign", ["--verify", "--deep", "--strict", app]);
      const bundleInfo =
        entry === apps[0] ? info : JSON.parse(exec("/usr/bin/plutil", ["-convert", "json", "-o", "-", path.join(app, "Info.plist")]));
      check(
        bundleInfo.CFBundleIdentifier === options["bundle-id"] || bundleInfo.CFBundleIdentifier.startsWith(`${options["bundle-id"]}.`),
        "Nested app/extension bundle ID is outside target",
      );
      const profile = exec("/usr/bin/security", ["cms", "-D", "-i", path.join(app, "embedded.mobileprovision")]);
      const extract = (key, format = "json") =>
        exec("/usr/bin/plutil", ["-extract", key, format, "-o", "-", "--", "-"], { input: profile }).trim();
      // Whole profiles contain date/data objects and cannot be converted directly to JSON.
      const permissions = JSON.parse(extract("Entitlements"));
      const teamIds = JSON.parse(extract("TeamIdentifier"));
      check(
        permissions["get-task-allow"] === false && !/<key>\s*(ProvisionedDevices|ProvisionsAllDevices)\s*<\/key>/.test(profile),
        "IPA is not signed with an App Store distribution profile",
      );
      check(new Date(extract("ExpirationDate", "raw")).getTime() > Date.now(), "Distribution profile has expired");
      const entitlementXML = exec("/usr/bin/codesign", ["-d", "--entitlements", "-", "--xml", app]);
      const entitlements = JSON.parse(exec("/usr/bin/plutil", ["-convert", "json", "-o", "-", "--", "-"], { input: entitlementXML }));
      check(entitlements["get-task-allow"] !== true, "Signed app permits debugger access");
      check(teamIds.includes(entitlements["com.apple.developer.team-identifier"]), "Signing team differs from distribution profile");
      check(
        entitlements["application-identifier"]?.endsWith(`.${bundleInfo.CFBundleIdentifier}`),
        "Signed application identifier differs from bundle ID",
      );
      check(entitlementAllowed(entitlements, permissions), "Signed app entitlements are not authorized by its profile");
      const prefix = path.join(temp, `signer-${verifiedBundles.length}-`);
      exec("/usr/bin/codesign", ["-d", `--extract-certificates=${prefix}`, app]);
      const certificate = fs.readFileSync(`${prefix}0`);
      const certXML = extract("DeveloperCertificates", "xml1");
      const allowed = [...certXML.matchAll(/<data>([\s\S]*?)<\/data>/g)].map((m) => Buffer.from(m[1].replace(/\s/g, ""), "base64"));
      check(
        allowed.some((c) => c.equals(certificate)),
        "Signing certificate is not authorized by distribution profile",
      );
      verifiedBundles.push({ bundleId: bundleInfo.CFBundleIdentifier, teamId: entitlements["com.apple.developer.team-identifier"] });
    }
  } finally {
    fs.rmSync(temp, { recursive: true, force: true });
  }
  return {
    sha256: expectedHash,
    bytes: bytes.length,
    bundleId: info.CFBundleIdentifier,
    version: String(info.CFBundleShortVersionString),
    buildNumber: String(info.CFBundleVersion),
    verifiedBundles,
  };
}

export function uploadIPA(filename, auth, exec = nativeExec) {
  const text = exec(
    "xcrun",
    [
      "altool",
      "--upload-package",
      filename,
      "--api-key",
      auth.keyId,
      "--api-issuer",
      auth.issuer,
      "--p8-file-path",
      auth.keyPath,
      "--output-format",
      "json",
    ],
    { timeout: 30 * 60 * 1000 },
  );
  let output;
  try {
    output = JSON.parse(text);
  } catch {
    throw new Pending("Upload command returned without a parseable receipt; reconcile before retrying");
  }
  check(!output["product-errors"]?.length, "Apple rejected the binary upload (native diagnostic omitted from receipt)");
  return { deliveryId: output["delivery-uuid"] ?? output.deliveryId ?? null };
}

async function buildUpload(api, t, input, options, receipt, deps) {
  const facts = (deps.verifyIPA ?? verifyIPA)(input.ipa, input.ipaHash, options);
  let build = await findBuild(api, options);
  if (!build) {
    if (receipt.data.build) {
      check(
        receipt.data.build.sha256 === facts.sha256,
        "Previously attempted IPA hash differs; do not retry a different artifact under this build number",
      );
      throw new Pending("Previous upload intent exists but exact build is not visible; use status and reconcile before retrying");
    }
    receipt.data.build = { ...facts, state: "upload_intent" };
    receipt.save("build_upload_intent", facts);
    try {
      const delivery = await (deps.uploadIPA ?? uploadIPA)(input.ipa, deps.auth);
      receipt.data.build = { ...receipt.data.build, ...delivery, state: "transport_returned" };
      receipt.save("build_transport_returned", delivery);
    } catch (_e) {
      receipt.save("build_upload_uncertain");
      throw new Pending("Binary upload result requires reconciliation; use status with the same target/receipt before retrying");
    }
  } else {
    if (receipt.data.build) check(receipt.data.build.sha256 === facts.sha256, "Build receipt artifact hash mismatch");
    receipt.save("build_found", {
      id: build.id,
      processingState: attrs(build).processingState,
      artifactBytesConfirmed: false,
      localUploadAttemptRecorded: !!receipt.data.build,
    });
  }
  build = await poll(
    async () => {
      const b = await findBuild(api, options);
      check(!b || !["FAILED", "INVALID"].includes(attrs(b).processingState), `Build ${options["build-number"]} failed processing`);
      return b;
    },
    (b) => b && attrs(b).processingState === "VALID",
    options,
    deps.sleep,
    "Binary processing",
  );
  check(attrs(build).expired !== true, "Build has expired");
  if (options.associate)
    check(attrs(build).buildAudienceType !== "INTERNAL_ONLY", "Internal-only build cannot be associated with an App Store version");
  let associated = (await api(`/v1/appStoreVersions/${t.version.id}/relationships/build`)).data?.id === build.id;
  if (options.associate && !associated) {
    check(EDITABLE.has(attrs(t.version).appVersionState), "Selected draft is not editable");
    receipt.save("build_association_intent", { buildId: build.id, versionId: t.version.id });
    await api(`/v1/appStoreVersions/${t.version.id}/relationships/build`, "PATCH", { data: link("builds", build.id) });
    await poll(
      () => api(`/v1/appStoreVersions/${t.version.id}/relationships/build`),
      (d) => d.data?.id === build.id,
      options,
      deps.sleep,
      "Build association readback",
    );
    associated = true;
  }
  const result = {
    status: "verified",
    scope: options.associate ? "processed_build_and_association" : "processed_build",
    buildId: build.id,
    processingState: "VALID",
    associated,
    versionId: t.version.id,
    localArtifactSha256: facts.sha256,
    artifactBytesConfirmed: false,
    localUploadAttemptRecorded: !!receipt.data.build,
  };
  receipt.save("build_verified", result);
  return result;
}
export async function observe(api, t, options, input) {
  const library = (await optional(api, `/v1/apps/${t.app.id}/assetLibrary`)).data;
  const localizations = [];
  for (const loc of t.localizations) {
    const modern = library ? await placements(api, loc.id) : [];
    const sets = list(await all(api, `/v1/appStoreVersionLocalizations/${loc.id}/appScreenshotSets?limit=200`));
    const legacy = [];
    for (const set of sets) {
      const items = list(await all(api, `/v1/appScreenshotSets/${set.id}/appScreenshots?limit=200`));
      legacy.push({
        setId: set.id,
        display: attrs(set).screenshotDisplayType,
        items: items.map((x) => ({ id: x.id, fileName: attrs(x).fileName, state: attrs(x).assetDeliveryState?.state })),
      });
    }
    localizations.push({
      locale: attrs(loc).locale,
      id: loc.id,
      modernScreenshots: screenshotEvidence(modern),
      legacyScreenshotSets: legacy,
    });
  }
  const build = await findBuild(api, options);
  const associated = (await api(`/v1/appStoreVersions/${t.version.id}/relationships/build`)).data?.id ?? null;
  let screenshotsStatus = input.screenshots.length ? "not_verified" : "missing_local_artifacts";
  if (input.screenshots.length && library) {
    const groups = screenshotGroups(await api("/v1/appAssetLibraryRefData"), input.screenshots);
    let verified = true;
    for (const group of groups) {
      const loc = t.localizations.find((x) => attrs(x).locale === group.locale);
      if (!loc || !matches(await placements(api, loc.id, group.group), group)) verified = false;
    }
    screenshotsStatus = verified
      ? "verified"
      : localizations.some((l) => l.modernScreenshots.length || l.legacyScreenshotSets.some((s) => s.items.length))
        ? "unverified_existing"
        : "missing_remote";
  }
  if (input.screenshotErrors.length) screenshotsStatus = "invalid_local_artifacts";
  return {
    status: "observed",
    overall: "incomplete",
    localScreenshotErrors: input.screenshotErrors,
    screenshotsStatus,
    requestedScreenshotCount: input.screenshotEntryCount,
    previewCountNotUploaded: input.previewCount,
    target: targetIdentity(options),
    versionId: t.version.id,
    versionState: attrs(t.version).appVersionState,
    libraryId: library?.id ?? null,
    localizations,
    build: build ? { id: build.id, processingState: attrs(build).processingState, associated: build.id === associated } : null,
    associatedBuildId: associated,
  };
}
export async function run(options, deps = {}) {
  const input = loadManifest(options);
  const identity = targetIdentity(options);
  if (options.command === "plan")
    return {
      status: "planned",
      overall: "incomplete",
      screenshotsStatus: input.screenshots.length ? "not_started" : "missing_local_artifacts",
      target: identity,
      manifestSha256: input.manifestSha256,
      screenshotCount: input.screenshots.length,
      locales: [...new Set(input.screenshots.map((x) => x.locale))],
      distributionIPAAvailable: !!input.ipa,
      previewCountNotUploaded: input.previewCount,
      remoteVerified: false,
    };
  const auth = deps.auth ?? (deps.api ? undefined : credentials());
  const api = deps.api ?? createAPI(auth);
  const sleep = deps.sleep ?? ((ms) => new Promise((resolve) => setTimeout(resolve, ms)));
  const fetcher = deps.fetch ?? fetch;
  const t = await target(api, options);
  const receipt = new Receipt(options.receipt, identity, input.manifestSha256);
  try {
    if (options.command === "status") {
      const result = await observe(api, t, options, input);
      receipt.save("status_readback", result);
      return result;
    }
    check(EDITABLE.has(attrs(t.version).appVersionState), "Requested version is not an editable draft");
    if (options.command === "build") return await buildUpload(api, t, input, options, receipt, { ...deps, auth, sleep });
    check(input.screenshots.length > 0, "Manifest has no app_store_screenshot entries");
    const library = (await optional(api, `/v1/apps/${t.app.id}/assetLibrary`)).data;
    let result;
    if (options["media-mode"] === "legacy") result = await legacyScreenshots(api, t, input.screenshots, options, receipt, fetcher, sleep);
    else {
      check(library?.id, "No modern Asset Library; choose --media-mode legacy explicitly with per-file asc_display_type");
      const groups = screenshotGroups(await api("/v1/appAssetLibraryRefData"), input.screenshots);
      result = await modernScreenshots(api, t, library, groups, options, receipt, fetcher, sleep);
    }
    return { ...result, previewCountNotUploaded: input.previewCount };
  } catch (e) {
    receipt.save(e instanceof Pending ? "pending_external" : "failed", { command: options.command });
    throw e;
  }
}
const HELP = `ShippyKit Apple draft uploader (Node 18+, no dependencies)\n\nnode deploy/apple-upload.mjs <plan|status|screenshots|build> \\\n  --release-output release-output --app-id ID --bundle-id com.example.app \\\n  --version 1.0 --build-number 1\n\nOptional: --binary-version 1.0.0 (defaults to --version); --receipt PATH;\n--timeout-seconds 600; --poll-seconds 10; --replace; --media-mode auto|modern|legacy;\n--ipa PATH --ipa-sha256 HASH; --associate (build only).\n\nplan: local manifest checks only. status: read modern placements AND legacy sets.\nscreenshots: modern upload + processing + exact localization/group/order readback.\nLegacy is explicit and requires manifest asc_display_type; modern conflicts stop it.\nbuild: verify signed IPA, upload using xcrun altool, reconcile processing; --associate\nattaches only the selected draft and verifies readback. No App Review/release calls.\n\nTeam key env: ASC_KEY_ID, ASC_ISSUER_ID, ASC_KEY_PATH (EMBER_ASC_* fallback).\nDefault key path: ~/.appstoreconnect/private_keys/AuthKey_<ID>.p8.\nReceipt defaults to release-output/apple-upload-receipt.json. Preserve it on retry.\nExit 0: operation verified/planned/observed; exit 2: pending external; exit 1: failed.\nOnly screenshots are uploaded; previews, listing text, privacy and review are separate.\n`;
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
