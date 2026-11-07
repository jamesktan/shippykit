# Public website, hosting and domains

Store listings link to a public marketing page, a support page and a privacy policy. ShippyKit builds that site, hosts it on **Railway**, and connects a domain registered with **Squarespace Domains**. This is separate from the local asset website in [PREVIEW.md](PREVIEW.md).

Buying, renewing or transferring a domain stays with the owner, and so do sign-ins. Within an authorized website task, the agent may create the Railway project and services, deploy, and connect a domain the owner bought, including its DNS records and redirect.

## Quick path: connect the domain with the helper

Use this once the site is deployed on Railway (sections 1 and 2 cover building and deploying it). The helper does every check and every change. You only run commands and relay messages.

1. Run:

   ```sh
   python3 deploy/domains.py status --domain example.com
   ```

   Use the bare domain the owner bought, without `www.`.
2. Read the last lines. They start with `NEXT [agent]`, `NEXT [wait]`, `NEXT [owner]` or `NEXT [done]`.
   - **`NEXT [agent]`**: run the command on the `$` line exactly as shown, then go back to step 1. If the command contains `<project-id>` or `<service-name>`, run `python3 deploy/domains.py projects` first and use the web service's values (not `Postgres`).
   - **`NEXT [wait]`**: tell the user what it is waiting for. Rerun step 1 after the minutes it gives. Change nothing in the meantime.
   - **`NEXT [owner]`**: give the user the message word for word. Stop until they say it is done, then go back to step 1.
   - **`NEXT [done]`**: report the live address. You are finished.
3. If a helper command itself prints `OWNER ACTION:` or exits with code 3, treat it like `NEXT [owner]`. If it prints `ERROR:` or exits with code 1, report the message and stop. Exit code 2 from `squarespace` means another agent is using the desktop: wait 3 minutes and rerun it.

Do not change DNS, Railway domains or the Squarespace dashboard by hand while using the helper, and never paste secrets into a command. The helper saves its progress (no secrets) in `release-output/domains/<domain>.json`, so a later session can continue with step 1.

What the helper's commands do:

| Command | Effect |
| --- | --- |
| `status` | Read-only. Checks Railway sign-in, the custom domain, the certificate, the nameservers, the records on Squarespace's servers and on public DNS, HTTPS on `/`, `/support` and `/privacy`, the canonical address and the bare-domain redirect. |
| `projects` | Read-only. Lists Railway workspaces, projects, services and IDs. |
| `railway` | Adds `www.<domain>` to the service if it is missing, and saves the CNAME and TXT records Railway asks for. Safe to repeat. |
| `squarespace` | Opens its own background Chrome window through [Cua Driver](CUA-DRIVER.md). It removes the "Squarespace Defaults" parking preset, adds the missing records and adds a permanent, path-keeping redirect from the bare domain to `www`, reading each change back. It then closes its window. Safe to repeat; `--dry-run` only lists what it would change. |

The `squarespace` command stops for the owner when Squarespace shows "Verify to continue". It sends a notification and waits up to 5 minutes for the sign-in. It also stops when the Mac is locked, because macOS hides windows from automation then; when Chrome is signed out; or when an existing record conflicts with Railway's. It never deletes custom records.

## 1. Build or reuse the site

Reuse an existing site and its deploy route. Otherwise create a small one in `website/` with these routes:

- `/`, the marketing page
- `/support`, for help and a way to make contact
- `/privacy`, the privacy policy
- `/terms`, the terms of use
- `/healthz`, which Railway's health check calls

Take the product claims and media from the app and `release-output/`: real captures, accurate copy, the current store status ("Coming soon" until the app is live). The privacy policy must describe the app's actual data handling, from the same evidence as Apple's App Privacy or Play's Data safety answers. Present the privacy policy and terms to the owner as drafts for their review, not as legal advice.

Ask the owner how support should work: a published email address, or a contact form. A form needs storage (Railway Postgres with no public TCP proxy), a same-origin check, rate limits and a honeypot. Its logs must not contain emails, message text or IP addresses. Skip analytics, cookies and third-party requests unless the app already uses them and the policy says so. Set a canonical address from an environment variable (`PUBLIC_ORIGIN`) so it can move to the custom domain without a code change.

## 2. Deploy on Railway

Check access read-only first: `railway whoami --json`, then `python3 deploy/domains.py projects`. New projects go in the workspace the owner uses for apps; on this Mac that is the personal "James Tan's Projects".

```sh
railway init --name <app>-website --workspace <workspace-id> --json   # run inside website/
railway add --database postgres --json                                # only for a contact form
railway add --service <app>-site --variables 'NODE_ENV=production' \
  --variables 'DATABASE_URL=${{Postgres.DATABASE_URL}}' --json
railway domain --service <app>-site --port 8080 --json                # the *.up.railway.app address
railway variable set PUBLIC_ORIGIN=https://<that address> --service <app>-site --skip-deploys
railway up ./website --path-as-root --project <project-id> --service <app>-site \
  --environment production --detach
```

Configure the Dockerfile builder, a `/healthz` health check and restart on failure. Railway stops reading `railway.toml` config files after 2026-12-01; `railway config migrate` converts them. Watch the deploy with `railway deployment list --service <service> --json` and `railway logs --service <service>`. It is done when it reports `SUCCESS` and the five routes answer over HTTPS. Record the workspace, project, environment, service IDs and deploy command in APP.md and the site's README.

`railway variable list` and its `--kv` form print secret values, including the database password inside `DATABASE_URL`. Print variable names only, for example by piping `--json` output through a filter that keeps the keys. Rotate any secret that has been printed.

## 3. Manual reference: what the helper does

Use this to understand the helper's output, or when the domain's DNS is not hosted at Squarespace (`status` then lists the records to add there).

**Railway.** The helper adds `www.<domain>`, not the bare domain: `railway domain www.<domain> --port <port> --service … --project … --environment … --json`. Railway answers with a CNAME `www` → `<random>.up.railway.app` and a TXT `_railway-verify.www` holding `railway-verify=<token>`. The TXT value is public DNS, not a secret. Squarespace's bare-domain records do not work reliably with Railway's verification and certificates ([Squarespace root domains](https://station.railway.com/questions/connect-squarespace-domain-to-railway-a2315cd9), [workaround](https://station.railway.com/feedback/squarespace-domains-can-be-added-to-rail-3b873d6a), [apex verification](https://station.railway.com/questions/apex-domain-verification-bug-write-up-11ebfed2)), so the bare domain redirects to `www` instead. `railway domain status <host> … --json` reports verification and the certificate. Its `dnsRecords[].currentValue` can lag behind real DNS, so the helper asks the nameservers directly with `dig`.

**Squarespace dashboard.** Squarespace has no public DNS API; its developer platform covers commerce only. The helper therefore drives the dashboard with Cua Driver, following the shared-browser rules in [CUA-DRIVER.md](CUA-DRIVER.md#5-use-during-deployment). Pages: `https://account.squarespace.com/domains/managed/<domain>/dns/dns-settings` and `…/<domain>/website`. On the DNS page it deletes the **Squarespace Defaults** preset, whose bare-domain A records and `www` → `ext-sq.squarespace.com` CNAME point at a parking page. It keeps **Email Security** (SPF `v=spf1 -all` and a reject DMARC policy, which stop spoofed mail when the domain sends none) and **Squarespace Domain Connect**. It adds each record with **ADD RECORD**: the `TYPE` combo box, the type option, `NAME`, then `DATA` (labeled `TEXT` for TXT records), then **save record**. On the Website page, **Add domain forwarding url** with `SUBDOMAIN` `@`, the URL `https://www.<domain>`, and under **Advanced settings**, **Permanent Redirect (301)** and **Maintain paths**. A saved rule appears with REDIRECT TYPE "Permanent redirect" and PATH FORWARDING "Forward path". Deleting a preset and adding a redirect can each trigger "Verify to continue as <owner email>", which is the owner's Google sign-in.

**Timing.** A newly bought domain can take several minutes to appear at its registry. On 2026-10-29, Squarespace's nameservers and the public resolvers served new records within minutes. Squarespace says a redirect can take 24–48 hours to start, though it is usually much sooner.

## 4. After the domain is live

`status` checks the site's canonical address. If it still names the `*.up.railway.app` address, set `PUBLIC_ORIGIN` to `https://www.<domain>` and redeploy. Changing the marketing, support and privacy URLs in App Store Connect or Play Console is a store edit, so it follows the run's store authorization. Keep the `*.up.railway.app` address working until the store links have moved. Record in APP.md: registrar, DNS host, Railway project/service/domain IDs, the records, the redirect and the verification time. Never record Railway tokens, database URLs, or Squarespace or Google session data.
