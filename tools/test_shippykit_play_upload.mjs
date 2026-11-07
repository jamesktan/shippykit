import assert from "node:assert/strict";
import crypto from "node:crypto";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { deflateSync } from "node:zlib";
import { loadInputs, Pending, parseArgs, parseListing, run, serviceAccountToken } from "../docs/launch/harness/deploy/play-upload.mjs";

const PKG = "com.example.game";
const sha = (b) => crypto.createHash("sha256").update(b).digest("hex");
function crc(bytes) {
  let c = 0xffffffff;
  for (const b of bytes) {
    c ^= b;
    for (let k = 0; k < 8; k++) c = (c >>> 1) ^ (c & 1 ? 0xedb88320 : 0);
  }
  return (c ^ 0xffffffff) >>> 0;
}
function png(w, h, color = 1, alpha = false) {
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
// Stored (uncompressed) ZIP; the verifier only reads the central directory.
function zip(files) {
  const locals = [];
  const central = [];
  let offset = 0;
  for (const [name, data] of files) {
    const n = Buffer.from(name);
    const local = Buffer.alloc(30);
    local.writeUInt32LE(0x04034b50, 0);
    local.writeUInt32LE(data.length, 18);
    local.writeUInt32LE(data.length, 22);
    local.writeUInt16LE(n.length, 26);
    const entry = Buffer.alloc(46);
    entry.writeUInt32LE(0x02014b50, 0);
    entry.writeUInt32LE(data.length, 20);
    entry.writeUInt32LE(data.length, 24);
    entry.writeUInt16LE(n.length, 28);
    entry.writeUInt32LE(offset, 42);
    locals.push(local, n, data);
    central.push(entry, n);
    offset += 30 + n.length + data.length;
  }
  const directory = Buffer.concat(central);
  const end = Buffer.alloc(22);
  end.writeUInt32LE(0x06054b50, 0);
  end.writeUInt16LE(files.length, 8);
  end.writeUInt16LE(files.length, 10);
  end.writeUInt32LE(directory.length, 12);
  end.writeUInt32LE(offset, 16);
  return Buffer.concat([...locals, directory, end]);
}
function aab({ signed = true, filler = 64 } = {}) {
  const files = [
    ["BundleConfig.pb", Buffer.from("config")],
    ["base/manifest/AndroidManifest.xml", Buffer.from("manifest")],
    ["base/dex/classes.dex", crypto.randomBytes(filler)],
  ];
  if (signed) files.push(["META-INF/UPLOAD.RSA", Buffer.from("signature")]);
  return zip(files);
}
const LISTING =
  "# Store listing\n\n## Title\nEmber Flight\n\n## Short description\nFly a dragon through a burning world.\n\n## Description\nGlide over ash fields.\n\nRescue villages.\n\n## Release notes\nSmoother depth scenery.\n";

function fixture(t, { listing = LISTING, screenshots = 3, bundle = aab() } = {}) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "shippykit-play-test-"));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const files = [];
  const add = (relative, bytes, extra = {}) => {
    fs.mkdirSync(path.dirname(path.join(root, relative)), { recursive: true });
    fs.writeFileSync(path.join(root, relative), bytes);
    files.push({ path: relative, sha256: sha(bytes), bytes: bytes.length, platform: "android", ...extra });
    return bytes;
  };
  add("stores/android/en-US/listing.md", Buffer.from(listing), { kind: "store_copy", locale: "en-US" });
  const shots = [];
  // Manifest order is the reverse of file order, so upload order must follow `order`.
  for (let i = 0; i < screenshots; i++)
    shots.unshift(
      sha(
        add(`stores/android/en-US/phone/0${i + 1}.png`, png(400, 720, i + 1), {
          kind: "app_store_screenshot",
          play_image_type: "phoneScreenshots",
          order: screenshots - i,
        }),
      ),
    );
  const feature = add("stores/android/en-US/feature-graphic.png", png(1024, 500, 9), {
    kind: "promo_image",
    play_image_type: "featureGraphic",
  });
  fs.mkdirSync(path.join(root, "builds/android/14"), { recursive: true });
  fs.writeFileSync(path.join(root, "builds/android/14/game.aab"), bundle);
  const manifest = {
    files,
    android_bundle: { path: "builds/android/14/game.aab", sha256: sha(bundle), version_code: 14, package_name: PKG },
  };
  const save = () => fs.writeFileSync(path.join(root, "manifest.json"), JSON.stringify(manifest));
  save();
  return {
    root,
    manifest,
    add,
    save,
    shots,
    feature: sha(feature),
    bundle,
    events: () => JSON.parse(fs.readFileSync(path.join(root, "play-upload-receipt.json"), "utf8")).events.map((e) => e.event),
    options: (command, ...extra) => parseArgs([command, "--release-output", root, "--package", PKG, ...extra]),
  };
}

// In-memory Edits API: each edit copies the committed state; commit replaces it.
function fakePlay({ versionCode = 14, live = {} } = {}) {
  let state = { bundles: [], tracks: { internal: [], alpha: [], beta: [] }, listings: {}, images: {}, ...structuredClone(live) };
  const edits = new Map();
  const sessions = new Map();
  const calls = [];
  const ranges = [];
  const control = { intercept: null, acceptOnce: 0 };
  let n = 0;
  const reply = (status, doc, headers = {}) =>
    new Response(doc === undefined ? null : JSON.stringify(doc), { status, headers: { "content-type": "application/json", ...headers } });
  const fail = (status, code, reason = code) =>
    reply(status, { error: { code: status, status: code, message: `${reason} (fake)`, details: [{ reason }] } });
  async function request(input, init = {}) {
    const url = new URL(input);
    const method = init.method ?? "GET";
    assert.equal(init.headers.Authorization, "Bearer TEST_TOKEN");
    const body = init.body == null ? Buffer.alloc(0) : Buffer.from(init.body);
    const upload = url.searchParams.get("upload_id");
    if (upload) {
      calls.push("PUT session");
      const session = sessions.get(upload);
      const range = init.headers["Content-Range"];
      ranges.push(range);
      const [, start, , total] = /^bytes (\d+)-(\d+)\/(\d+)$/.exec(range);
      assert.equal(Number(start), session.bytes.length);
      session.bytes = Buffer.concat([session.bytes, body]);
      if (control.acceptOnce) {
        session.bytes = session.bytes.subarray(0, control.acceptOnce);
        control.acceptOnce = 0;
      }
      if (session.bytes.length < Number(total))
        return new Response(null, { status: 308, headers: { range: `bytes=0-${session.bytes.length - 1}` } });
      const bundle = { versionCode, sha1: crypto.createHash("sha1").update(session.bytes).digest("hex"), sha256: sha(session.bytes) };
      session.edit.bundles.push(bundle);
      return reply(200, bundle);
    }
    const m = /^\/(?:upload\/)?androidpublisher\/v3\/applications\/([^/]+)\/edits(?:\/([^/:]+))?(?::(validate|commit))?(\/.*)?$/.exec(
      url.pathname,
    );
    assert.ok(m, url.pathname);
    assert.equal(decodeURIComponent(m[1]), PKG);
    const [, , id, action, rest] = m;
    const route = !id ? `${method} /edits` : `${method} ${rest ? decodeURIComponent(rest) : action ? `:${action}` : "edit"}`;
    calls.push(route);
    const intercepted = control.intercept?.(route);
    if (intercepted) return intercepted;
    if (!id) {
      const editId = `edit-${++n}`;
      edits.set(editId, structuredClone(state));
      return reply(200, { id: editId, expiryTimeSeconds: "4102444800" });
    }
    const edit = edits.get(id);
    if (!edit) return fail(404, "NOT_FOUND");
    if (action === "validate") return reply(200, { id });
    if (action === "commit") {
      assert.equal(url.searchParams.get("changesInReviewBehavior"), "ERROR_IF_IN_REVIEW");
      state = edit;
      edits.delete(id);
      return reply(200, { id });
    }
    if (!rest) {
      assert.equal(method, "DELETE");
      edits.delete(id);
      return new Response(null, { status: 204 });
    }
    const parts = rest.split("/").slice(1).map(decodeURIComponent);
    const json = () => JSON.parse(body.toString("utf8"));
    if (parts[0] === "bundles") {
      if (method === "GET") return reply(200, { kind: "androidpublisher#bundlesListResponse", bundles: edit.bundles });
      assert.equal(url.searchParams.get("uploadType"), "resumable");
      const session = `s${++n}`;
      sessions.set(session, { edit, bytes: Buffer.alloc(0) });
      return reply(200, undefined, {
        location: `https://androidpublisher.googleapis.com/upload/androidpublisher/v3/applications/${PKG}/edits/${id}/bundles?uploadType=resumable&upload_id=${session}`,
      });
    }
    if (parts[0] === "tracks") {
      // Google omits empty arrays.
      const shape = (track, releases) => ({ track, ...(releases.length ? { releases } : {}) });
      if (parts.length === 1) return reply(200, { tracks: Object.entries(edit.tracks).map(([track, releases]) => shape(track, releases)) });
      const track = parts[1];
      if (method === "GET") return edit.tracks[track] ? reply(200, shape(track, edit.tracks[track])) : fail(404, "NOT_FOUND");
      assert.equal(method, "PUT");
      const doc = json();
      assert.equal(doc.track, track);
      for (const release of doc.releases)
        for (const code of release.versionCodes)
          if (!edit.bundles.some((b) => String(b.versionCode) === code)) return fail(400, "INVALID_ARGUMENT");
      edit.tracks[track] = doc.releases;
      return reply(200, doc);
    }
    if (parts[0] === "listings") {
      if (parts.length === 1) return reply(200, { listings: Object.values(edit.listings) });
      const language = parts[1];
      if (parts.length === 2) {
        if (method === "GET") return edit.listings[language] ? reply(200, edit.listings[language]) : fail(404, "NOT_FOUND");
        if (method === "PATCH") {
          if (!edit.listings[language]) return fail(404, "NOT_FOUND");
          Object.assign(edit.listings[language], json());
        } else {
          assert.equal(method, "PUT");
          edit.listings[language] = { ...json(), language };
        }
        return reply(200, edit.listings[language]);
      }
      edit.images[`${language}/${parts[2]}`] ??= [];
      const images = edit.images[`${language}/${parts[2]}`];
      if (method === "GET") return reply(200, images.length ? { images } : {});
      if (method === "DELETE") return reply(200, { deleted: images.splice(0) });
      assert.equal(method, "POST");
      assert.equal(url.searchParams.get("uploadType"), "media");
      assert.match(init.headers["Content-Type"], /^image\/(png|jpeg)$/);
      const image = { id: `img-${++n}`, url: `https://play-lh.googleusercontent.com/${n}`, sha256: sha(body) };
      images.push(image);
      return reply(200, { image });
    }
    assert.fail(`Unhandled ${route}`);
  }
  return {
    fetch: request,
    control,
    calls,
    ranges,
    edits,
    fail,
    get live() {
      return state;
    },
  };
}
const deps = (play, extra = {}) => ({ fetch: play.fetch, token: async () => "TEST_TOKEN", sleep: async () => {}, ...extra });
const writes = (play) => play.calls.filter((c) => !c.startsWith("GET "));
const ALL = ["--parts", "bundle,listing,images"];

test("plan checks the manifest, copy, images and AAB without credentials or network", async (t) => {
  const f = fixture(t);
  const result = await run(f.options("plan"), { fetch: () => assert.fail("network"), token: () => assert.fail("token") });
  assert.equal(result.status, "planned");
  assert.deepEqual(result.bundle, { versionCode: "14", sha256: sha(f.bundle), bytes: f.bundle.length });
  assert.deepEqual(result.listings[0].characters, {
    title: 12,
    shortDescription: 37,
    fullDescription: 40,
    releaseNotes: 23,
  });
  assert.deepEqual(result.images, [
    { locale: "en-US", type: "phoneScreenshots", count: 3 },
    { locale: "en-US", type: "featureGraphic", count: 1 },
  ]);
  assert.equal(fs.existsSync(path.join(f.root, "play-upload-receipt.json")), false);
});

test("arguments keep production, unknown parts and unscoped uploads out", () => {
  const base = ["--package", PKG];
  assert.throws(() => parseArgs(["upload", ...base]), /Required --parts/);
  assert.throws(() => parseArgs(["upload", ...base, "--parts", "bundle,video"]), /Invalid --parts/);
  assert.throws(() => parseArgs(["upload", ...base, "--parts", "bundle", "--track", "production"]), /Production/);
  assert.throws(() => parseArgs(["upload", ...base, "--parts", "bundle", "--track", "wear:production"]), /Production/);
  assert.throws(() => parseArgs(["upload", ...base, "--parts", "bundle", "--status", "inProgress"]), /draft or completed/);
  assert.throws(() => parseArgs(["status", ...base, "--commit"]), /--commit applies only to upload/);
  assert.throws(() => parseArgs(["plan", "--package", "not a package"]), /Invalid package/);
  assert.throws(() => parseArgs(["upload", ...base, "--parts", "bundle", "--aab", "x.aab"]), /go together/);
  const options = parseArgs(["upload", ...base, "--parts", "listing,images"]);
  assert.equal(options.track, "internal");
  assert.equal(options.status, "draft");
  assert.deepEqual(options.parts, ["listing", "images"]);
});

test("listing copy comes from the store-copy headings and is counted in Unicode characters", (t) => {
  assert.deepEqual(
    parseListing(
      "# Store listing\n\n## Name\nA\n\n## Subtitle\nignored\n\n## Full description\nB\n\n### Internal\nnot public\n\n## What's New in 1.1\nC\n",
    ),
    { title: "A", fullDescription: "B", releaseNotes: "C" },
  );
  assert.throws(() => parseListing("## Description\n```\ncode\n```\n"), /plain text/);
  assert.throws(() => parseListing("## Title\nA\n## Title\nB\n"), /Duplicate/);
  assert.throws(
    () => loadInputs(fixture(t, { listing: `## Title\n${"x".repeat(31)}\n` }).options("plan")),
    /title is 31 characters; Play allows 30/,
  );
  assert.equal(
    loadInputs(fixture(t, { listing: `## Title\n${"🔥".repeat(30)}\n` }).options("plan")).listings.get("en-US").fields.title.length,
    60,
  );
});

test("local checks refuse transparent screenshots, wrong graphic sizes, extreme ratios and unsigned bundles", (t) => {
  for (const [bytes, type, error] of [
    [png(400, 720, 1, true), "phoneScreenshots", /opaque/],
    [png(400, 900), "phoneScreenshots", /2:1 ratio/],
    [png(1024, 512), "featureGraphic", /1024x500/],
    [png(512, 512), "icon", /32-bit PNG with alpha/],
  ]) {
    const f = fixture(t);
    f.add(`stores/android/en-US/extra-${type}.png`, bytes, { kind: "promo_image", play_image_type: type });
    f.save();
    assert.throws(() => loadInputs(f.options("plan")), error);
  }
  assert.throws(() => loadInputs(fixture(t, { bundle: aab({ signed: false }) }).options("plan")), /no JAR signature/);
  const apk = zip([
    ["classes.dex", Buffer.from("dex")],
    ["META-INF/CERT.RSA", Buffer.from("signature")],
  ]);
  assert.throws(() => loadInputs(fixture(t, { bundle: apk }).options("plan")), /Not an Android App Bundle/);
  const tampered = fixture(t);
  tampered.manifest.android_bundle.sha256 = "0".repeat(64);
  tampered.save();
  assert.throws(() => loadInputs(tampered.options("plan")), /AAB hash mismatch/);
});

test("upload without --commit stages and validates one edit, then deletes it", async (t) => {
  const f = fixture(t);
  const play = fakePlay();
  const result = await run(f.options("upload", ...ALL), deps(play));
  assert.equal(result.status, "validated");
  assert.equal(result.committed, false);
  assert.deepEqual(
    Object.values(result.components).map((c) => c.status),
    ["verified", "verified", "verified"],
  );
  assert.ok(play.calls.includes("POST :validate"));
  assert.ok(!play.calls.includes("POST :commit"));
  assert.equal(play.edits.size, 0);
  assert.deepEqual(play.live.bundles, []);
  assert.deepEqual(play.live.listings, {});
});

test("upload --commit puts the bundle, draft release, listing and images in one commit and reads them back", async (t) => {
  const f = fixture(t);
  const play = fakePlay({
    live: {
      bundles: [{ versionCode: 13, sha256: "a".repeat(64) }],
      tracks: { internal: [{ name: "1.0 (13)", status: "completed", versionCodes: ["13"] }] },
    },
  });
  const result = await run(f.options("upload", ...ALL, "--commit"), deps(play));
  assert.equal(result.status, "verified");
  assert.equal(result.committed, true);
  assert.equal(result.components.bundle.artifactBytesConfirmed, true);
  assert.equal(play.calls.filter((c) => c === "POST :commit").length, 1);
  assert.ok(play.calls.indexOf("POST :commit") < play.calls.lastIndexOf("POST /edits"), "readback uses a fresh edit");
  assert.deepEqual(play.live.tracks.internal, [
    { name: "1.0 (13)", status: "completed", versionCodes: ["13"] },
    { versionCodes: ["14"], status: "draft", releaseNotes: [{ language: "en-US", text: "Smoother depth scenery." }] },
  ]);
  assert.deepEqual(play.live.listings["en-US"], {
    language: "en-US",
    title: "Ember Flight",
    shortDescription: "Fly a dragon through a burning world.",
    fullDescription: "Glide over ash fields.\n\nRescue villages.",
  });
  assert.deepEqual(
    play.live.images["en-US/phoneScreenshots"].map((x) => x.sha256),
    f.shots,
  );
  assert.deepEqual(
    play.live.images["en-US/featureGraphic"].map((x) => x.sha256),
    [f.feature],
  );
  assert.equal(play.edits.size, 0);
  const receipt = fs.readFileSync(path.join(f.root, "play-upload-receipt.json"), "utf8");
  assert.ok(!receipt.includes("TEST_TOKEN") && !receipt.includes("upload_id"));
  assert.deepEqual(JSON.parse(receipt).build, { versionCode: "14", sha256: sha(f.bundle), track: "internal", status: "draft" });
});

test("a rerun reuses the committed bundle and leaves matching copy, images and release alone", async (t) => {
  const f = fixture(t);
  const play = fakePlay();
  await run(f.options("upload", ...ALL, "--commit"), deps(play));
  play.calls.length = 0;
  const result = await run(f.options("upload", ...ALL, "--commit"), deps(play));
  assert.equal(result.status, "verified");
  assert.equal(result.unchanged, true);
  assert.equal(result.committed, false);
  assert.deepEqual(writes(play), ["POST /edits", "POST :validate", "DELETE edit"]);
});

test("unmatched remote screenshots need --replace, checked before any write", async (t) => {
  const f = fixture(t);
  const play = fakePlay({ live: { images: { "en-US/phoneScreenshots": [{ id: "old", sha256: "b".repeat(64) }] } } });
  await assert.rejects(run(f.options("upload", ...ALL, "--commit"), deps(play)), /1 image\(s\) not in the manifest; --replace is required/);
  assert.deepEqual(writes(play), ["POST /edits", "DELETE edit"]);
  assert.equal((await run(f.options("upload", ...ALL, "--commit", "--replace"), deps(play))).status, "verified");
  assert.deepEqual(
    play.live.images["en-US/phoneScreenshots"].map((x) => x.sha256),
    f.shots,
  );
});

test("screenshots already on Play keep a matching prefix; a wrong order is re-uploaded", async (t) => {
  const f = fixture(t);
  const prefix = fakePlay({ live: { images: { "en-US/phoneScreenshots": [{ id: "first", sha256: f.shots[0] }] } } });
  await run(f.options("upload", "--parts", "images", "--commit"), deps(prefix));
  assert.equal(prefix.calls.filter((c) => c === "POST /listings/en-US/phoneScreenshots").length, 2);
  assert.ok(!prefix.calls.includes("DELETE /listings/en-US/phoneScreenshots"));
  assert.equal(prefix.live.images["en-US/phoneScreenshots"][0].id, "first");
  const swapped = fakePlay({
    live: {
      images: {
        "en-US/phoneScreenshots": [
          { id: "b", sha256: f.shots[1] },
          { id: "a", sha256: f.shots[0] },
        ],
      },
    },
  });
  await run(f.options("upload", "--parts", "images", "--commit"), deps(swapped));
  assert.ok(swapped.calls.includes("DELETE /listings/en-US/phoneScreenshots"));
  assert.deepEqual(
    swapped.live.images["en-US/phoneScreenshots"].map((x) => x.sha256),
    f.shots,
  );
});

test("a versionCode that already holds other bytes is refused before upload", async (t) => {
  const f = fixture(t);
  const play = fakePlay({ live: { bundles: [{ versionCode: 14, sha256: "c".repeat(64) }] } });
  await assert.rejects(
    run(f.options("upload", "--parts", "bundle", "--commit"), deps(play)),
    /versionCode 14 already holds a different bundle/,
  );
  assert.deepEqual(writes(play), ["POST /edits", "DELETE edit"]);
});

test("Play reading another versionCode from the AAB stops before commit", async (t) => {
  const f = fixture(t);
  const play = fakePlay({ versionCode: 15 });
  await assert.rejects(
    run(f.options("upload", "--parts", "bundle", "--commit"), deps(play)),
    /Play read versionCode 15 from the AAB, not 14; nothing was committed/,
  );
  assert.deepEqual(play.live.bundles, []);
  assert.equal(play.edits.size, 0);
  assert.equal(f.events().at(-1), "failed");
});

test("another draft on the track needs --replace; a completed release supersedes only its own status", async (t) => {
  const f = fixture(t);
  const play = fakePlay({
    live: {
      bundles: [
        { versionCode: 12, sha256: "d".repeat(64) },
        { versionCode: 13, sha256: "e".repeat(64) },
      ],
      tracks: {
        internal: [
          { status: "completed", versionCodes: ["13"] },
          { status: "draft", versionCodes: ["12"] },
        ],
      },
    },
  });
  await assert.rejects(
    run(f.options("upload", "--parts", "bundle", "--commit"), deps(play)),
    /draft with versionCodes 12; --replace is required/,
  );
  await run(f.options("upload", "--parts", "bundle", "--commit", "--replace"), deps(play));
  const releases = () => play.live.tracks.internal.map((r) => [r.status, r.versionCodes]);
  assert.deepEqual(releases(), [
    ["completed", ["13"]],
    ["draft", ["14"]],
  ]);
  await run(f.options("upload", "--parts", "bundle", "--commit", "--status", "completed"), deps(play));
  assert.deepEqual(releases(), [["completed", ["14"]]]);
  await assert.rejects(
    run(f.options("upload", "--parts", "bundle", "--commit"), deps(play)),
    /versionCode 14 is already completed on internal/,
  );
  assert.deepEqual(releases(), [["completed", ["14"]]]);
});

test("changes already in review leave the run pending with nothing committed", async (t) => {
  const f = fixture(t);
  const play = fakePlay();
  play.control.intercept = (route) =>
    route === "POST :commit" ? play.fail(400, "FAILED_PRECONDITION", "CHANGES_ALREADY_IN_REVIEW") : undefined;
  await assert.rejects(
    run(f.options("upload", "--parts", "listing", "--commit"), deps(play)),
    (e) => e instanceof Pending && /already in review/.test(e.message),
  );
  assert.deepEqual(play.live.listings, {});
  assert.equal(play.edits.size, 0);
  assert.equal(f.events().at(-1), "pending_external");
});

test("an interrupted commit is pending and keeps its edit for reconciliation", async (t) => {
  const f = fixture(t);
  const play = fakePlay();
  play.control.intercept = (route) => {
    if (route === "POST :commit") throw new TypeError("fetch failed");
  };
  await assert.rejects(
    run(f.options("upload", "--parts", "listing", "--commit"), deps(play)),
    (e) => e instanceof Pending && /Commit outcome is unknown for edit edit-1/.test(e.message),
  );
  assert.equal(play.edits.size, 1);
  assert.deepEqual(f.events().slice(-2), ["commit_uncertain", "pending_external"]);
});

test("status compares Play with the manifest without writing and reports invalid local inputs", async (t) => {
  const f = fixture(t);
  const play = fakePlay();
  await run(f.options("upload", ...ALL, "--commit"), deps(play));
  play.live.listings["en-US"].shortDescription = "Edited in Console";
  play.calls.length = 0;
  const result = await run(f.options("status"), deps(play));
  assert.equal(result.status, "observed");
  assert.equal(result.overall, "incomplete");
  assert.equal(result.components.bundle.status, "verified");
  assert.deepEqual(result.components.listing.locales, [{ locale: "en-US", status: "differs", differs: ["shortDescription"] }]);
  assert.equal(result.components.images.status, "verified");
  assert.deepEqual(result.tracks.find((x) => x.track === "internal").releases, [{ name: null, status: "draft", versionCodes: ["14"] }]);
  assert.deepEqual(result.listingLocales, ["en-US"]);
  assert.deepEqual(writes(play), ["POST /edits", "DELETE edit"]);
  fs.writeFileSync(path.join(f.root, "stores/android/en-US/phone/01.png"), png(400, 720, 7));
  const again = await run(f.options("status"), deps(play));
  assert.equal(again.components.images.status, "invalid_local_artifacts");
  assert.match(again.localErrors[0].reason, /Image hash mismatch/);
});

test("bundle upload resumes from the byte range Play acknowledges", async (t) => {
  const bundle = aab({ filler: 700 * 1024 });
  const f = fixture(t, { bundle });
  const play = fakePlay();
  play.control.acceptOnce = 100 * 1024;
  const result = await run(f.options("upload", "--parts", "bundle"), deps(play, { chunkSize: 256 * 1024 }));
  assert.equal(result.status, "validated");
  assert.equal(result.components.bundle.artifactBytesConfirmed, true);
  const expected = [];
  for (let start = 0; start < bundle.length; ) {
    const end = Math.min(start + 256 * 1024, bundle.length);
    expected.push(`bytes ${start}-${end - 1}/${bundle.length}`);
    start = start === 0 ? 100 * 1024 : end;
  }
  assert.deepEqual(play.ranges, expected);
});

test("upload sessions outside Google's API hosts are refused", async (t) => {
  const f = fixture(t);
  const play = fakePlay();
  play.control.intercept = (route) =>
    route === "POST /bundles"
      ? new Response(null, { status: 200, headers: { location: "https://uploads.example.com/u?upload_id=1" } })
      : undefined;
  await assert.rejects(run(f.options("upload", "--parts", "bundle"), deps(play)), /Refusing non-Google Play API URL/);
});

test("rate-limited reads retry after the server's delay", async (t) => {
  const f = fixture(t);
  const play = fakePlay();
  let limited = false;
  play.control.intercept = (route) => {
    if (route !== "GET /bundles" || limited) return undefined;
    limited = true;
    return new Response(null, { status: 429, headers: { "retry-after": "7" } });
  };
  const waits = [];
  const result = await run(f.options("status", "--parts", "bundle"), deps(play, { sleep: async (ms) => waits.push(ms) }));
  assert.deepEqual(waits, [7000]);
  assert.equal(result.components.bundle.status, "missing_remote");
});

test("the service-account token is a cached RS256 assertion for the androidpublisher scope", async (t) => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "shippykit-play-key-"));
  t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
  const { privateKey, publicKey } = crypto.generateKeyPairSync("rsa", { modulusLength: 2048 });
  const key = {
    type: "service_account",
    client_email: "uploader@example.iam.gserviceaccount.com",
    private_key: privateKey.export({ type: "pkcs8", format: "pem" }),
    token_uri: "https://oauth2.googleapis.com/token",
  };
  const keyPath = path.join(dir, "key.json");
  fs.writeFileSync(keyPath, JSON.stringify(key));
  let calls = 0;
  const fetcher = async (url, init) => {
    calls++;
    assert.equal(String(url), "https://oauth2.googleapis.com/token");
    const form = new URLSearchParams(init.body);
    assert.equal(form.get("grant_type"), "urn:ietf:params:oauth:grant-type:jwt-bearer");
    const [head, claims, signature] = form.get("assertion").split(".");
    assert.ok(crypto.verify("sha256", Buffer.from(`${head}.${claims}`), publicKey, Buffer.from(signature, "base64url")));
    assert.equal(JSON.parse(Buffer.from(head, "base64url")).alg, "RS256");
    const c = JSON.parse(Buffer.from(claims, "base64url"));
    assert.equal(c.iss, key.client_email);
    assert.equal(c.scope, "https://www.googleapis.com/auth/androidpublisher");
    assert.equal(c.aud, "https://oauth2.googleapis.com/token");
    return new Response(JSON.stringify({ access_token: "ya29.test", expires_in: 3599 }), { status: 200 });
  };
  const token = serviceAccountToken({ keyPath }, fetcher);
  assert.equal(await token(), "ya29.test");
  assert.equal(await token(), "ya29.test");
  assert.equal(calls, 1);
  const elsewhere = path.join(dir, "elsewhere.json");
  fs.writeFileSync(elsewhere, JSON.stringify({ ...key, token_uri: "https://tokens.example.com/token" }));
  await assert.rejects(serviceAccountToken({ keyPath: elsewhere }, fetcher)(), /unexpected service-account token URI/);
});
