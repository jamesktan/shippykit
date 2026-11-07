# ShippyKit preview verification

Verified on 2026-10-23 using the existing Isofall 1.0.0 build 6 release manifest on Lexar. The app repository and its release assets were read only; the generated site was written to a temporary directory outside that repository.

- Included 11 images, two 20-second videos and one public listing from the manifest.
- Excluded build/signing artifacts, raw captures, review notes and unresolved store fields. Isofall's manifest had no icon entry, so the site showed an empty icon section; this run did not generate or replace the app's icon.
- Opened the site in the installed Playwright Chromium browser at 1440×1000 and 390×844. All images decoded; both videos advanced during playback. Neither viewport had horizontal overflow or page script errors. Inspected the desktop and mobile screenshots.
- Verified the public-copy download and direct `file://` opening. The loopback server returned 404 for the generated registry, manifest, build directory and deployment-state paths.
- Used only an owned loopback test server, stopped after verification. No ngrok endpoint was started and no store upload was performed by this verification.

All 18 helper regression tests passed on Python 3.14.8; both helper and tests also passed Python 3.9 grammar checks. A Python 3.9 runtime was not exercised. The repeatable suite covers public/private selection, nested Markdown sections, escaped HTML, icon/platform entries, explicit public copy, invalid hashes/formats, traversal/symlinks, output ownership, HTTP isolation, byte-range responses and normal client-disconnect handling:

```sh
python3 -m unittest discover -s tools -p 'test_shippykit_preview.py' -v
```

It uses temporary fixtures and Python's standard library. Browser checks above used real existing release media separately; fixture headers do not prove a video decoder or platform icon compiler accepts an asset. The icon-generation workflow is documented in [ICONS.md](../harness/deploy/ICONS.md); native icon integration and actual store acceptance remain per-app checks.
