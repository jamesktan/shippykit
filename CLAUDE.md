# ShippyKit

## gstack

This project uses [gstack](https://github.com/garrytan/gstack). Install: `git clone --single-branch --depth 1 https://github.com/garrytan/gstack.git ~/.claude/skills/gstack && cd ~/.claude/skills/gstack && ./setup` (requires Bun 1.4+).

- Use the `/browse` skill from gstack for all web browsing; never use `mcp__claude-in-chrome__*` tools.
- Available skills: /office-hours, /spec, /plan-ceo-review, /plan-eng-review, /plan-design-review, /design-consultation, /design-shotgun, /design-html, /review, /deslop-shared-libs, /test-audit, /ship, /land-and-deploy, /canary, /benchmark, /browse, /connect-chrome, /qa, /qa-only, /design-review, /scrape, /setup-browser-cookies, /setup-deploy, /setup-gbrain, /retro, /investigate, /document-release, /document-generate, /codex, /cso, /autoplan, /plan-devex-review, /devex-review, /careful, /freeze, /guard, /unfreeze, /gstack-upgrade, /learn.
- Workflow for new work: /office-hours → /autoplan (or the individual plan reviews) → build → /review → /qa → /ship.
