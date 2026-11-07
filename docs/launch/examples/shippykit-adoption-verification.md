# ShippyKit local installation and adoption verification

ShippyKit 0.1.0 was installed into three existing personal projects on 2026-10-23.
The installer adds Codex and Claude Code skills, deployment guides/helpers and a
portable install receipt. The core skill resumes from project memory; installing
it does not start a build, upload, review submission or public tunnel.

| Project | Installation commit | Adopted history |
| --- | --- | --- |
| Musiciles | `jamesktan/musicles` — `39efb7f` | Existing APP/STATE, both platforms' draft receipts, listing/media readbacks and unresolved pricing/declarations |
| Ember / Eimyrja | `jamesktan/ember` — `417ed788` | Existing agent handoff, Unity release tools, Apple media verification, prepared Play kit and website publication dependency |
| Isofall | `jamesktan/isofall` — `35a1764` | Existing APP/STATE, build-6 phone/store receipts, listing/media evidence and optional Android decision |

These are adopted historical records, not fresh remote verification. The new
Ember memory explicitly distinguishes recorded results from current inspection.
Musiciles and Isofall APP/STATE remained byte-identical through installation.
Ember's pre-existing ProjectSettings edit and external worktrees were preserved.
All commits above were pushed to each personal repository's `main`.

Verification performed:

- 55 installer, resume and preview tests passed on Python 3.9.6.
- The installer suite covers idempotence, dry-run, safe upgrades, custom-file
  conflicts, protected memory, separate agent selection and unsafe paths.
- The resume suite covers fresh, partial and uploaded projects, stale/mismatched
  artifacts, legacy handoffs, bounded discovery and private-file exclusions.
- An independent disposable-project run confirmed that status wrote nothing,
  adoption wrote only the discovery cache, an altered same-size artifact failed
  its hash check, and a past upload receipt remained cached/unverified.
- All 18 actual project skill entrypoints and the three resume/helper copies
  matched the package. Every install receipt listed both agents and zero active
  conflicts. Checked custom tools/evidence and meaningful symlinks were preserved.
- All 36 Musiciles and 57 Isofall manifest paths existed. This was presence
  verification, not a new signing/media/remote validation pass.
- Source Markdown links, shell syntax and the repository documentation check
  passed. Skill YAML was parsed with the installed Ruby YAML library; the bundled
  Python skill validator could not run because its optional PyYAML dependency was
  unavailable. ShippyKit itself uses only Python's standard library.

Existing copied Apple/Google/coordinator guides in Musiciles and Isofall matched
known historical ShippyKit source bytes. Those guides were upgraded, then the
installer reconciled their ownership. Custom helpers and project memory were
preserved. Future customized-file updates remain explicit merge candidates;
the receipt's active conflict list, not leftover candidate files, determines
which upgrades still need attention.
