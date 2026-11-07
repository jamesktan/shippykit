import assert from "node:assert/strict";
import crypto from "node:crypto";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { deflateSync } from "node:zlib";
import {
  APIError,
  createAPI,
  loadManifest,
  Pending,
  parseArgs,
  run,
  screenshotGroups,
  screenshotOrdering,
  uploadIPA,
  uploadParts,
  verifyIPA,
} from "../docs/launch/harness/deploy/apple-upload.mjs";

const refdata = JSON.parse(fs.readFileSync(new URL("./fixtures/apple-asset-refdata.json", import.meta.url)));
const sha = (b) => crypto.createHash("sha256").update(b).digest("hex");
const large = "IPHONE_DYNAMIC_ISLAND_LARGE_PROFILE",
  medium = "IPHONE_DYNAMIC_ISLAND_MEDIUM_PROFILE";
function crc(bytes) {
  let c = 0xffffffff;
  for (const b of bytes) {
    c ^= b;
    for (let k = 0; k < 8; k++) c = (c >>> 1) ^ (c & 1 ? 0xedb88320 : 0);
  }
  return (c ^ 0xffffffff) >>> 0;
}
function png(w = 1320, h = 2868, color = 1, alpha = false) {
  const chunk = (name, data) => {
    const tag = Buffer.from(name),
      b = Buffer.alloc(data.length + 12);
    b.writeUInt32BE(data.length);
    tag.copy(b, 4);
    data.copy(b, 8);
    b.writeUInt32BE(crc(Buffer.concat([tag, data])), 8 + data.length);
    return b;
  };
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(w);
  ihdr.writeUInt32BE(h, 4);
  ihdr[8] = 8;
  ihdr[9] = alpha ? 6 : 2;
  const raw = Buffer.alloc(h * (w * (alpha ? 4 : 3) + 1), color);
  for (let y = 0; y < h; y++) raw[y * (w * (alpha ? 4 : 3) + 1)] = 0;
  return Buffer.concat([
    Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]),
    chunk("IHDR", ihdr),
    chunk("IDAT", deflateSync(raw)),
    chunk("IEND", Buffer.alloc(0)),
  ]);
}
function fixture(t, count = 2) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "shippykit-upload-test-"));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const entries = [];
  for (let i = 0; i < count; i++) {
    const file = `stores/ios/en-US/iphone-6.9/${i}.png`,
      bytes = png(1320, 2868, i + 1);
    fs.mkdirSync(path.dirname(path.join(root, file)), { recursive: true });
    fs.writeFileSync(path.join(root, file), bytes);
    entries.push({ kind: "app_store_screenshot", path: file, sha256: sha(bytes), bytes: bytes.length });
  }
  const manifest = { bundle_identifier: "com.example.app", locale: "en-US", files: entries };
  const save = () => fs.writeFileSync(path.join(root, "manifest.json"), JSON.stringify(manifest));
  save();
  const options = (cmd) =>
    parseArgs([
      cmd,
      "--release-output",
      root,
      "--app-id",
      "123",
      "--bundle-id",
      "com.example.app",
      "--version",
      "1.0",
      "--build-number",
      "7",
      "--timeout-seconds",
      "0.002",
      "--poll-seconds",
      "0.001",
    ]);
  return { root, manifest, save, options };
}
function fakeApple() {
  const calls = [],
    images = [],
    placements = [],
    sets = [],
    legacy = [];
  let seq = 0;
  let associated = null;
  const builds = [];
  let library = true,
    breakOrder = false,
    processing = false,
    interruptCommit = false;
  const obj = (type, id, attributes, relationships = {}) => ({ type, id, attributes, relationships });
  const app = obj("apps", "123", { bundleId: "com.example.app" }),
    version = obj("appStoreVersions", "v1", { versionString: "1.0", platform: "IOS", appVersionState: "PREPARE_FOR_SUBMISSION" }),
    loc = obj("appStoreVersionLocalizations", "loc1", { locale: "en-US" });
  const response = (data, included = []) => ({ data: structuredClone(data), included: structuredClone(included) });
  const api = async (input, method = "GET", payload) => {
    calls.push({ input, method, payload });
    const u = new URL(input, "https://api.appstoreconnect.apple.com"),
      p = u.pathname;
    const a = payload?.data?.attributes,
      r = payload?.data?.relationships;
    if (p === "/v1/apps/123") return response(app);
    if (p === "/v1/apps/123/appStoreVersions") return response([version]);
    if (p === "/v1/appStoreVersions/v1/appStoreVersionLocalizations") return response([loc]);
    if (p === "/v1/apps/123/assetLibrary") {
      if (!library) throw new APIError(404, []);
      return response(obj("appAssetLibraries", "lib1", {}));
    }
    if (p === "/v1/appAssetLibraryRefData") return structuredClone(refdata);
    if (p === "/v1/appAssetLibraries/lib1/images") return response(images);
    if (p === "/v1/appStoreVersionLocalizations/loc1/placements") {
      const g = u.searchParams.get("filter[placementGroup]");
      const type = u.searchParams.get("filter[placementType]");
      return response(
        placements.filter((x) => (!g || x.attributes.placementGroup === g) && (!type || x.attributes.placementType === type)),
        images,
      );
    }
    if (p === "/v1/appAssetLibraryImages" && method === "POST") {
      const image = obj("appAssetLibraryImages", `img${++seq}`, {
        ...a,
        state: "AWAITING_UPLOAD",
        uploadOperations: [
          {
            method: "PUT",
            url: "https://store.example.test/SECRET_SIGNED_URL",
            offset: 0,
            length: a.fileSize,
            requestHeaders: [{ name: "Content-Type", value: "image/png" }],
          },
        ],
      });
      images.push(image);
      return response(image);
    }
    if (p.startsWith("/v1/appAssetLibraryImages/")) {
      const image = images.find((x) => x.id === p.split("/").at(-1));
      assert.ok(image);
      if (method === "PATCH") {
        if (interruptCommit) {
          interruptCommit = false;
          throw new Error("interrupted commit");
        }
        image.attributes.state = processing ? "UPLOAD_COMPLETE" : "PREPARE_FOR_SUBMISSION";
        image.attributes.specId = "bd402f1a-26ee-5b83-9dd7-972c60c43d47";
      }
      return response(image);
    }
    if (p === "/v1/appAssetLibraryPlacements" && method === "POST") {
      const placement = obj("appAssetLibraryPlacements", `p${++seq}`, { ...a, state: "PARENT_PREPARE_FOR_SUBMISSION" }, { image: r.image });
      placements.push(placement);
      return response(placement);
    }
    if (p.startsWith("/v1/appAssetLibraryPlacements/") && method === "DELETE") {
      placements.splice(
        placements.findIndex((x) => x.id === p.split("/").at(-1)),
        1,
      );
      return {};
    }
    if (p === "/v1/appAssetLibraryPlacementOrderingRequests") {
      const ids = r.orderedPlacements.data.map((x) => x.id);
      const ordered = ids.map((id) => placements.find((x) => x.id === id));
      // Apple: "All placements in the 'orderedPlacements' relationship must have the same 'placementType'."
      if (new Set(ordered.map((x) => x?.attributes.placementType)).size !== 1)
        throw new APIError(409, ["ENTITY_ERROR.RELATIONSHIP.INVALID"]);
      if (!breakOrder) {
        // Only the listed placements move; other placements keep their positions.
        const slots = placements.flatMap((x, i) => (ids.includes(x.id) ? [i] : []));
        slots.forEach((slot, k) => {
          placements[slot] = ordered[k];
        });
      } else placements.reverse();
      return response(obj("appAssetLibraryPlacementOrderingRequests", "order1", {}));
    }
    if (p === "/v1/appStoreVersionLocalizations/loc1/appScreenshotSets") return response(sets);
    if (p === "/v1/appScreenshotSets" && method === "POST") {
      const set = obj("appScreenshotSets", `set${++seq}`, a);
      sets.push(set);
      return response(set);
    }
    if (/^\/v1\/appScreenshotSets\/[^/]+\/appScreenshots$/.test(p)) return response(legacy.filter((x) => x.setId === p.split("/")[3]));
    if (p === "/v1/appScreenshots" && method === "POST") {
      const asset = obj("appScreenshots", `legacy${++seq}`, {
        ...a,
        assetDeliveryState: { state: "AWAITING_UPLOAD" },
        uploadOperations: [{ method: "PUT", url: "https://store.example.test/SECRET_SIGNED_URL", offset: 0, length: a.fileSize }],
      });
      asset.setId = r.appScreenshotSet.data.id;
      legacy.push(asset);
      return response(asset);
    }
    if (p.startsWith("/v1/appScreenshots/")) {
      const asset = legacy.find((x) => x.id === p.split("/").at(-1));
      if (method === "PATCH") {
        asset.attributes.assetDeliveryState = { state: "COMPLETE" };
        asset.attributes.sourceFileChecksum = a.sourceFileChecksum;
      }
      if (method === "DELETE") {
        legacy.splice(legacy.indexOf(asset), 1);
        return {};
      }
      return response(asset);
    }
    if (p.includes("/relationships/appScreenshots")) {
      const ids = payload.data.map((x) => x.id);
      legacy.sort((a, b) => ids.indexOf(a.id) - ids.indexOf(b.id));
      return {};
    }
    if (p === "/v1/builds") return response(builds, [obj("preReleaseVersions", "pre1", { version: "1.0", platform: "IOS" })]);
    if (p === "/v1/appStoreVersions/v1/relationships/build") {
      if (method === "PATCH") associated = payload.data.id;
      return { data: associated ? { id: associated, type: "builds" } : null };
    }
    throw new Error(`Unexpected fake route ${method} ${input}`);
  };
  return {
    api,
    calls,
    images,
    placements,
    version,
    loc,
    sets,
    legacy,
    builds,
    get associated() {
      return associated;
    },
    set associated(v) {
      associated = v;
    },
    set library(v) {
      library = v;
    },
    set breakOrder(v) {
      breakOrder = v;
    },
    set processing(v) {
      processing = v;
    },
    set interruptCommit(v) {
      interruptCommit = v;
    },
    addPreview(group) {
      const preview = obj(
        "appAssetLibraryPlacements",
        `preview${++seq}`,
        { placementType: "APP_PREVIEW", placementGroup: group, state: "ACTIVE" },
        { video: { data: { type: "appAssetLibraryVideos", id: "video1" } } },
      );
      placements.unshift(preview);
      return preview;
    },
    addBuild(state = "VALID") {
      const b = obj("builds", "build1", { version: "7", processingState: state }, { preReleaseVersion: { data: { id: "pre1" } } });
      builds.push(b);
      return b;
    },
  };
}
const deps = (f) => ({
  api: f.api,
  fetch: async (_url, init) => {
    assert.equal(init.headers.Authorization, undefined);
    assert.equal(init.redirect, "error");
    return { ok: true };
  },
  sleep: (ms) => new Promise((resolve) => setTimeout(resolve, ms)),
});

test("local plan supports both manifest schemas; empty media never means complete", async (t) => {
  const f = fixture(t, 0);
  f.manifest.artifacts = f.manifest.files;
  delete f.manifest.files;
  f.save();
  const r = await run(f.options("plan"));
  assert.equal(r.overall, "incomplete");
  assert.equal(r.screenshotsStatus, "missing_local_artifacts");
  assert.equal(r.remoteVerified, false);
  assert.equal(fs.existsSync(path.join(f.root, "apple-upload-receipt.json")), false);
});
test("actual-schema catalog maps exact image dimensions and fails ambiguity or count overflow", (t) => {
  const f = fixture(t);
  const input = loadManifest(f.options("plan"));
  assert.equal(screenshotGroups(refdata, input.screenshots)[0].group, large);
  const med = { ...input.screenshots[0], width: 1206, height: 2622 };
  assert.equal(screenshotGroups(refdata, [med])[0].group, medium);
  assert.throws(
    () =>
      screenshotGroups(
        refdata,
        [...Array(11)].map(() => input.screenshots[0]),
      ),
    /Too many/,
  );
  assert.throws(() => screenshotGroups(refdata, [{ ...med, width: 1 }]), /0 eligible/);
});
test("manifest rejects traversal, symlinks, modified bytes, alpha, and ignores Android", (t) => {
  const f = fixture(t, 1);
  const item = f.manifest.files[0];
  const original = item.path;
  item.path = "../outside.png";
  f.save();
  assert.throws(() => loadManifest(f.options("plan")), /Unsafe/);
  item.path = original;
  item.sha256 = "0".repeat(64);
  f.save();
  assert.throws(() => loadManifest(f.options("plan")), /hash mismatch/);
  const data = png(1320, 2868, 1, true);
  fs.writeFileSync(path.join(f.root, original), data);
  item.sha256 = sha(data);
  item.bytes = data.length;
  f.save();
  assert.throws(() => loadManifest(f.options("plan")), /opaque/);
  fs.unlinkSync(path.join(f.root, original));
  fs.symlinkSync("/etc/hosts", path.join(f.root, original));
  assert.throws(() => loadManifest(f.options("plan")), /Symlink/);
  item.platform = "android";
  f.save();
  assert.equal(loadManifest(f.options("plan")).screenshots.length, 0);
});
test("modern screenshots upload, process, place, order, read back and rerun with no mutation", async (t) => {
  const f = fixture(t),
    remote = fakeApple();
  const r = await run(f.options("screenshots"), deps(remote));
  assert.equal(r.status, "verified");
  assert.equal(r.mode, "modern");
  assert.equal(remote.images.length, 2);
  assert.equal(remote.placements.length, 2);
  const before = remote.calls.length;
  await run(f.options("screenshots"), deps(remote));
  assert.ok(remote.calls.slice(before).every((c) => c.method === "GET"));
  const receipt = fs.readFileSync(path.join(f.root, "apple-upload-receipt.json"), "utf8");
  assert.ok(!receipt.includes("SECRET_SIGNED_URL"));
  assert.ok(!receipt.includes("uploadOperations"));
  assert.match(receipt, /screenshots_verified/);
});
test("status includes modern placements when legacy sets are empty and does not write remotely", async (t) => {
  const f = fixture(t),
    remote = fakeApple();
  await run(f.options("screenshots"), deps(remote));
  remote.addBuild();
  remote.associated = "build1";
  const before = remote.calls.length;
  const r = await run(f.options("status"), deps(remote));
  assert.equal(r.localizations[0].modernScreenshots.length, 2);
  assert.equal(r.localizations[0].legacyScreenshotSets.length, 0);
  assert.equal(r.screenshotsStatus, "verified");
  assert.equal(r.build.associated, true);
  assert.ok(remote.calls.slice(before).every((c) => c.method === "GET"));
});
test("status with empty local artifacts remains incomplete even with a valid remote build", async (t) => {
  const f = fixture(t, 0),
    remote = fakeApple();
  remote.addBuild();
  remote.associated = "build1";
  const r = await run(f.options("status"), deps(remote));
  assert.equal(r.screenshotsStatus, "missing_local_artifacts");
  assert.equal(r.overall, "incomplete");
});
test("modern resume after transfer/commit interruption reuses reservation and never reserves duplicate", async (t) => {
  const f = fixture(t, 1),
    remote = fakeApple();
  remote.interruptCommit = true;
  await assert.rejects(run(f.options("screenshots"), deps(remote)), /interrupted/);
  assert.equal(remote.images.length, 1);
  const result = await run(f.options("screenshots"), deps(remote));
  assert.equal(result.status, "verified");
  assert.equal(remote.images.length, 1);
});
test("processing and wrong order cannot report verified", async (t) => {
  const f = fixture(t),
    remote = fakeApple();
  remote.processing = true;
  await assert.rejects(run(f.options("screenshots"), deps(remote)), Pending);
  assert.equal(remote.placements.length, 0);
  remote.processing = false;
  remote.images[0].attributes.state = "PREPARE_FOR_SUBMISSION";
  remote.breakOrder = true;
  await assert.rejects(run(f.options("screenshots"), deps(remote)), Pending);
});
test("replacement requires explicit flag and prepares new assets before deleting old placements", async (t) => {
  const f = fixture(t, 1),
    remote = fakeApple();
  await run(f.options("screenshots"), deps(remote));
  const item = f.manifest.files[0],
    bytes = png(1320, 2868, 9);
  fs.writeFileSync(path.join(f.root, item.path), bytes);
  item.sha256 = sha(bytes);
  item.bytes = bytes.length;
  f.save();
  const before = remote.calls.length;
  await assert.rejects(run(f.options("screenshots"), deps(remote)), /--replace/);
  assert.ok(remote.calls.slice(before).every((c) => c.method === "GET"));
  const options = f.options("screenshots");
  options.replace = true;
  await run(options, deps(remote));
  const calls = remote.calls.slice(before);
  assert.ok(
    calls.findIndex((c) => c.method === "PATCH" && c.input.includes("appAssetLibraryImages")) <
      calls.findIndex((c) => c.method === "DELETE"),
  );
  assert.equal(remote.placements.length, 1);
});
test("screenshot ordering never includes previews and stops on an unknown screenshot", () => {
  const p = (id, placementType) => ({ id, attributes: { placementType } });
  const peers = [p("v1", "APP_PREVIEW"), p("s2", "APP_SCREENSHOT"), p("v2", "APP_PREVIEW"), p("s1", "APP_SCREENSHOT")];
  assert.deepEqual(screenshotOrdering(peers, ["s1", "s2", "s3"]), ["s1", "s2", "s3"]);
  assert.throws(() => screenshotOrdering([p("x", "APP_SCREENSHOT")], ["s1"]), /changed concurrently/);
});
test("a preview in the same group keeps its place through upload and replacement", async (t) => {
  const f = fixture(t),
    remote = fakeApple();
  const preview = remote.addPreview(large);
  assert.equal((await run(f.options("screenshots"), deps(remote))).status, "verified");
  const item = f.manifest.files[1],
    bytes = png(1320, 2868, 9);
  fs.writeFileSync(path.join(f.root, item.path), bytes);
  item.sha256 = sha(bytes);
  item.bytes = bytes.length;
  f.save();
  const options = f.options("screenshots");
  options.replace = true;
  assert.equal((await run(options, deps(remote))).status, "verified");
  const orders = remote.calls.filter((c) => c.input === "/v1/appAssetLibraryPlacementOrderingRequests");
  assert.equal(orders.length, 2);
  for (const c of orders) assert.ok(!c.payload.data.relationships.orderedPlacements.data.some((x) => x.id === preview.id));
  assert.deepEqual(
    remote.placements.map((x) => x.attributes.placementType),
    ["APP_PREVIEW", "APP_SCREENSHOT", "APP_SCREENSHOT"],
  );
  assert.equal(remote.placements[0].id, preview.id);
  assert.ok(!remote.calls.some((c) => c.method === "DELETE" && c.input.endsWith(`/${preview.id}`)));
});
test("legacy compatibility stops on modern placements and otherwise verifies MD5 and order", async (t) => {
  const f = fixture(t, 1),
    remote = fakeApple();
  await run(f.options("screenshots"), deps(remote));
  const options = f.options("screenshots");
  options["media-mode"] = "legacy";
  await assert.rejects(run(options, deps(remote)), /Modern placements/);
  remote.placements.length = 0;
  f.manifest.files[0].asc_display_type = "APP_IPHONE_67";
  f.save();
  const r = await run(options, deps(remote));
  assert.equal(r.mode, "legacy_compatibility");
  assert.equal(remote.legacy[0].attributes.sourceFileChecksum.length, 32);
});
test("build associates existing exact valid binary without uploading; repeat is GET-only", async (t) => {
  const f = fixture(t, 0),
    remote = fakeApple();
  remote.addBuild();
  const options = f.options("build");
  options.associate = true;
  const d = {
    ...deps(remote),
    verifyIPA: () => ({ sha256: "1".repeat(64), bytes: 1 }),
    uploadIPA: () => assert.fail("must not upload existing build"),
  };
  const first = await run(options, d);
  assert.equal(first.associated, true);
  assert.equal(first.artifactBytesConfirmed, false);
  const before = remote.calls.length;
  await run(options, d);
  assert.ok(remote.calls.slice(before).every((c) => c.method === "GET"));
});
test("build records intent before native call and never uploads twice after ambiguous result", async (t) => {
  const f = fixture(t, 0),
    remote = fakeApple();
  let uploads = 0;
  const d = {
    ...deps(remote),
    verifyIPA: () => ({ sha256: "2".repeat(64) }),
    uploadIPA: () => {
      uploads++;
      const receipt = JSON.parse(fs.readFileSync(path.join(f.root, "apple-upload-receipt.json")));
      assert.equal(receipt.build.state, "upload_intent");
      throw new Error("lost connection SECRET");
    },
  };
  await assert.rejects(run(f.options("build"), d), Pending);
  await assert.rejects(run(f.options("build"), d), Pending);
  assert.equal(uploads, 1);
  remote.addBuild();
  const r = await run(f.options("build"), d);
  assert.equal(r.status, "verified");
  assert.equal(uploads, 1);
  assert.ok(!fs.readFileSync(path.join(f.root, "apple-upload-receipt.json"), "utf8").includes("SECRET"));
});
test("binary upload success remains pending until Apple reports VALID", async (t) => {
  const f = fixture(t, 0),
    remote = fakeApple();
  const d = {
    ...deps(remote),
    verifyIPA: () => ({ sha256: "3".repeat(64) }),
    uploadIPA: () => {
      remote.addBuild("PROCESSING");
      return { deliveryId: "delivery1" };
    },
  };
  await assert.rejects(run(f.options("build"), d), Pending);
  assert.equal(remote.associated, null);
  remote.builds[0].attributes.processingState = "INVALID";
  await assert.rejects(run(f.options("build"), d), /failed processing/);
});
test("explicit target does not choose another editable version; receipt cannot cross apps", async (t) => {
  const f = fixture(t),
    remote = fakeApple();
  remote.version.attributes.versionString = "2.0";
  await assert.rejects(run(f.options("status"), deps(remote)), /exactly one/);
  remote.version.attributes.versionString = "1.0";
  await run(f.options("status"), deps(remote));
  const doc = JSON.parse(fs.readFileSync(path.join(f.root, "apple-upload-receipt.json")));
  doc.target.appId = "999";
  fs.writeFileSync(path.join(f.root, "apple-upload-receipt.json"), JSON.stringify(doc));
  await assert.rejects(run(f.options("status"), deps(remote)), /another target/);
});
test("upload parts reject gaps and credential headers; no JWT sent to signed URL", async () => {
  const resource = {
    attributes: { uploadOperations: [{ method: "PUT", url: "https://example.test/SECRET", offset: 0, length: 3, requestHeaders: [] }] },
  };
  let count = 0;
  await uploadParts(resource, Buffer.from("abc"), async (_u, o) => {
    count++;
    assert.deepEqual(o.headers, {});
    assert.equal(o.body.toString(), "abc");
    return { ok: true };
  });
  assert.equal(count, 1);
  resource.attributes.uploadOperations[0].offset = 1;
  await assert.rejects(
    uploadParts(resource, Buffer.from("abc"), () => assert.fail()),
    /ranges/,
  );
  resource.attributes.uploadOperations[0].offset = 0;
  resource.attributes.uploadOperations[0].requestHeaders = [{ name: "Authorization", value: "secret" }];
  await assert.rejects(
    uploadParts(resource, Buffer.from("abc"), () => assert.fail()),
    /credential/,
  );
});
test("API JWT is scoped to Apple and refuses cross-origin pagination/redirect", async (t) => {
  const f = fixture(t, 0),
    { privateKey } = crypto.generateKeyPairSync("ec", { namedCurve: "prime256v1" }),
    keyPath = path.join(f.root, "key.p8");
  fs.writeFileSync(keyPath, privateKey.export({ type: "pkcs8", format: "pem" }));
  const api = createAPI({ keyId: "KEY", issuer: "issuer", keyPath }, async (url, request) => {
    assert.equal(url.origin, "https://api.appstoreconnect.apple.com");
    assert.equal(request.redirect, "error");
    const jwt = request.headers.Authorization.slice(7).split(".");
    assert.equal(Buffer.from(jwt[2], "base64url").length, 64);
    assert.equal(JSON.parse(Buffer.from(jwt[1], "base64url")).aud, "appstoreconnect-v1");
    return { ok: true, status: 200, text: async () => '{"data":[]}' };
  });
  await api("/v1/apps");
  await assert.rejects(api("https://evil.test/v1/apps"), /non-Apple/);
});
test("native IPA verifier checks profile date, team, entitlements and actual certificate", (t) => {
  const f = fixture(t, 0),
    ipa = path.join(f.root, "App.ipa");
  fs.writeFileSync(ipa, "fixture");
  const options = f.options("build");
  let codesign = false;
  let tamper = false;
  const entitlements = {
    "get-task-allow": false,
    "application-identifier": "TEAM.com.example.app",
    "com.apple.developer.team-identifier": "TEAM",
    "com.apple.developer.associated-domains": ["applinks:example.com"],
  };
  const exec = (cmd, args, extra) => {
    if (cmd.endsWith("unzip") && args[0] === "-Z1") return "Payload/App.app/Info.plist\n";
    if (cmd.endsWith("unzip") && args[0] === "-Z") return "-rw-r--r-- info\n";
    if (cmd.endsWith("unzip") && args[0] === "-p") return "INFO";
    if (cmd.endsWith("plutil") && args[0] === "-extract") {
      if (args[1] === "Entitlements") return JSON.stringify({ ...entitlements, "com.apple.developer.associated-domains": "*" });
      if (args[1] === "TeamIdentifier") return '["TEAM"]';
      if (args[1] === "ExpirationDate") return "2099-01-01T00:00:00Z";
      if (args[1] === "DeveloperCertificates")
        return `<array><data>${Buffer.from(tamper ? "wrong" : "certificate").toString("base64")}</data></array>`;
    }
    if (cmd.endsWith("plutil"))
      return JSON.stringify(
        extra.input === "INFO"
          ? {
              CFBundleIdentifier: "com.example.app",
              CFBundleShortVersionString: "1.0",
              CFBundleVersion: "7",
              CFBundleSupportedPlatforms: ["iPhoneOS"],
            }
          : entitlements,
      );
    if (cmd.endsWith("codesign")) {
      codesign = true;
      const cert = args.find((x) => x.startsWith("--extract-certificates="));
      if (cert) fs.writeFileSync(`${cert.slice(cert.indexOf("=") + 1)}0`, "certificate");
      return "ENTITLEMENTS";
    }
    if (cmd.endsWith("security")) return "<plist>PROFILE</plist>";
    return "";
  };
  assert.equal(verifyIPA(ipa, sha(Buffer.from("fixture")), options, exec).verifiedBundles[0].teamId, "TEAM");
  assert.equal(codesign, true);
  assert.throws(() => verifyIPA(ipa, "0".repeat(64), options, exec), /hash mismatch/);
  assert.throws(() => verifyIPA(ipa, sha(Buffer.from("fixture")), { ...options, "binary-version": "2.0" }, exec), /differs/);
  tamper = true;
  assert.throws(() => verifyIPA(ipa, sha(Buffer.from("fixture")), options, exec), /certificate is not authorized/);
});
test("altool uses current native flags and existing key path; returns only delivery ID", () => {
  const result = uploadIPA("/tmp/App.ipa", { keyId: "KEY", issuer: "ISSUER", keyPath: "/private/auth.p8" }, (cmd, args) => {
    assert.equal(cmd, "xcrun");
    assert.deepEqual(args, [
      "altool",
      "--upload-package",
      "/tmp/App.ipa",
      "--api-key",
      "KEY",
      "--api-issuer",
      "ISSUER",
      "--p8-file-path",
      "/private/auth.p8",
      "--output-format",
      "json",
    ]);
    return JSON.stringify({ "delivery-uuid": "delivery1", password: "MUSTNOTRETURN" });
  });
  assert.deepEqual(result, { deliveryId: "delivery1" });
});
test("build ignores broken capture while status reports it and still reads the remote build", async (t) => {
  const f = fixture(t, 1),
    remote = fakeApple();
  fs.unlinkSync(path.join(f.root, f.manifest.files[0].path));
  remote.addBuild();
  let verified = 0;
  const d = {
    ...deps(remote),
    verifyIPA: () => {
      verified++;
      return { sha256: "5".repeat(64) };
    },
    uploadIPA: () => assert.fail("existing build"),
  };
  assert.equal((await run(f.options("build"), d)).status, "verified");
  assert.equal(verified, 1);
  const status = await run(f.options("status"), d);
  assert.equal(status.build.id, "build1");
  assert.equal(status.screenshotsStatus, "invalid_local_artifacts");
  assert.equal(status.localScreenshotErrors.length, 1);
  await assert.rejects(run(f.options("screenshots"), d), /ENOENT/);
});
test("ACTIVE live placement state verifies; non-digest names are existing unverified media", async (t) => {
  const f = fixture(t, 1),
    remote = fakeApple();
  await run(f.options("screenshots"), deps(remote));
  remote.placements[0].attributes.state = "ACTIVE";
  assert.equal((await run(f.options("status"), deps(remote))).screenshotsStatus, "verified");
  remote.images[0].attributes.fileName = "iphone-6.9-01-isofall.png";
  const before = remote.calls.length;
  assert.equal((await run(f.options("status"), deps(remote))).screenshotsStatus, "unverified_existing");
  assert.ok(remote.calls.slice(before).every((c) => c.method === "GET"));
});
test("build refuses expired and internal-only builds before draft association", async (t) => {
  const f = fixture(t, 0),
    remote = fakeApple();
  const b = remote.addBuild();
  const options = f.options("build");
  options.associate = true;
  const d = { ...deps(remote), verifyIPA: () => ({ sha256: "6".repeat(64) }) };
  b.attributes.expired = true;
  await assert.rejects(run(options, d), /expired/);
  b.attributes.expired = false;
  b.attributes.buildAudienceType = "INTERNAL_ONLY";
  await assert.rejects(run(options, d), /Internal-only/);
  assert.equal(remote.associated, null);
});
