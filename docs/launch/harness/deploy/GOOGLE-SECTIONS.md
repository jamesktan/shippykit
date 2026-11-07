# Review every Google Play section

Use the [shared section workflow](README.md#review-every-store-section) and [Google Play playbook](GOOGLE-PLAY.md). Review the actual selected app in Play Console, choose the best accurate answer supported by evidence, save within the user's existing scope, and tell the user what you chose. Ask about uncertain facts, then apply and verify their answer. This review does not itself authorize review submission, tester distribution, or production release.

A full ShippyKit deployment includes the section sweep below. An explicitly bounded task, such as a binary upload or one questionnaire, inspects only the requested sections and their dependencies; report that limited coverage. A read-only review records findings and proposed answers without saving changes.

Official references below were checked on **2026-10-23**. Recheck the linked guidance and the live question wording when executing; Console navigation, forms and requirements change. This is a discovery guide, not proof that a fixed checklist covers the app.

## Discover the actual Console

1. Confirm the developer account, package name, app, requested track and versionCode. Read existing APP/STATE decisions and pending Console changes before editing. Keep another window's app or active edit untouched.
2. Enumerate the app's actual sidebar sections, dashboard tasks, tabs, expandable cards, locale selectors and release details. Open each section and read its current values, options, explanatory text and warnings. Record unavailable or permission-blocked sections as unread with the precise dependency.
3. On **App content**, visit both **Needs attention** and **Actioned**. A previous completed declaration is evidence to inspect, not a reason to skip it. Read every question page and the final summary. [App content guidance](https://support.google.com/googleplay/android-developer/answer/9859455?hl=en).
4. Revisit conditional forms after an answer, uploaded bundle, audience/country choice or account eligibility change reveals more questions. Continue until no newly revealed section remains unexamined; record any still-blocked branch.
5. Include optional sections in the inventory, but leave unused products, experiments, services and distribution programs unchanged. Mark them reviewed and not applicable with a reason; visiting them is not permission to activate them.

Use the existing authorized Console route for forms the API does not expose. API reads can verify supported fields, but an API result or local preflight cannot establish that every Console section was visited. If access is unavailable, continue independent work and report the coverage gap.

## Google-specific decisions

Use these starting points, then add every actual section discovered. Preserve valid owner decisions and unchanged saved values; do not replace them merely because another option is available.

| Section | Evidence and choice |
| --- | --- |
| Dashboard, policy status and messages | Read active tasks, deadlines, rejection details and eligibility restrictions. Follow the actual issue to its section; do not dismiss a warning because a build uploaded successfully. |
| Main/custom store listings and store settings | Check title, descriptions, category/tags, locale coverage, graphics, screenshots, support contacts and website/privacy links against the actual app and approved business facts. Preserve unrelated locales/custom listings. Verify public URLs work and belong to the app. [Listing setup](https://support.google.com/googleplay/android-developer/answer/9859152?hl=en). |
| App access / sign-in details | Check every restricted journey, including paid access, roles, location/device restrictions and external authentication. Supply working review instructions and an authorized review account when needed; verify the route works. Absence of a login screen does not prove unrestricted access. Keep credentials in secure storage and enter them only in the intended private Console fields. |
| Ads | Inspect runtime behavior, dependencies, remote configuration and ad/house-promotion features. Select the accurate answer from that evidence; do not equate “no purchases” with “no ads.” [Ads declaration examples](https://support.google.com/googleplay/android-developer/answer/9859455?hl=en). |
| Data safety | Audit app code, manifests, actual SDK versions/configuration, controlled web content, network behavior and backend handling. Map collection/sharing, purposes, optionality and security to Google's definitions. Include third-party behavior and relevant ephemeral off-device processing; absence of accounts or direct developer collection does not establish “no data.” [Data safety definitions](https://support.google.com/googleplay/android-developer/answer/10787469?hl=en). |
| Account/data deletion | Determine whether account creation is supported, including linked flows. Check the actual in-app deletion route, public request URL and backend retention/deletion behavior when required. Do not claim deletion because an uninstall removes local files. [Deletion requirements](https://support.google.com/googleplay/android-developer/answer/13327111?hl=en). |
| Content rating / IARC | Read and answer the entire questionnaire from shipped content, user-generated content, communication, purchases, advertising and other features it asks about. Review the calculated territorial ratings; do not pick a desired rating or change truthful answers to lower it. Revisit when relevant content changes. [Rating questionnaire](https://support.google.com/googleplay/android-developer/answer/9859655?hl=en). |
| Target audience and Families | Use the app's intended audience and actual design, distinct from its calculated rating. Do not select every age group for reach or exclude children merely to avoid requirements. Check the conditional Families, ads and age-screen questions. Ask if intended audience is not established. [Audience guidance](https://support.google.com/googleplay/android-developer/answer/9867159?hl=en). |
| Health, financial, government and other category declarations | Read each displayed declaration even for an app without those features. Evidence can support an accurate negative answer; an unknown is never a default No. Follow any requested documentation and category-specific questions. [Health](https://support.google.com/googleplay/android-developer/answer/14738291?hl=en), [financial features](https://support.google.com/googleplay/android-developer/answer/13849271?hl=en), [government information](https://support.google.com/googleplay/android-developer/answer/9514050?hl=en). |
| Sensitive permissions and conditional policies | Inspect the release bundle's merged permissions/services and actual feature use, including SDK additions. Follow displayed forms for such areas as advertising ID, location, photo/video access, SMS/call logs, accessibility, foreground services, VPN, news, or child safety. Do not claim a core use case unsupported by the app. Revisit after bundle processing. [Permission declarations](https://support.google.com/googleplay/android-developer/answer/9214102?hl=en). |
| Countries, pricing and products | Reuse established price, markets and monetization decisions; ask when business intent is unresolved. Inspect country synchronization between tracks and any conditional regional requirements. Do not default to free/worldwide: an app already offered free cannot simply become paid. Preserve products/subscriptions outside scope. [Prices](https://support.google.com/googleplay/android-developer/answer/6334373?hl=en), [country targeting](https://support.google.com/googleplay/android-developer/answer/7550024?hl=en). |
| App integrity/signing and device support | Confirm existing Play App Signing/upload certificates and relevant supported form factors against the intended AAB. Inspect device exclusions and bundle issues without changing keys, protection settings or supported devices merely to clear a task. Follow the playbook's signing checks. |
| Testing and production access | Inspect the exact track, tester eligibility, country settings and real testing history. Preserve the selected audience. Complete production-access answers from actual tests and feedback; never invent testers or dates. Record unmet external gates. [Personal-account testing](https://support.google.com/googleplay/android-developer/answer/14151465?hl=en). |
| Release details and Publishing overview | Verify AAB/versionCode, release notes, draft/rollout state, pending changes, review status and publishing mode. Review all affected changes before any transition; a saved form, accepted bundle or completed questionnaire is not an approved/public app. [Publishing controls](https://support.google.com/googleplay/android-developer/answer/9859654?hl=en). |

## Choose, inform, or ask

- Apply supported factual choices under existing authorization without asking for blanket owner confirmation. For example, a complete app/SDK/configuration audit can support the ads answer. Explain consequential selections and the evidence briefly as work proceeds; include a grouped summary at handoff.
- For Data safety, check backend and SDK facts that source code alone cannot establish. If retention, sharing, encryption or deployment configuration is unknown, ask that specific question instead of assuming the safest-looking checkbox.
- For an uncertain choice, record the actual question/options, what is known, the missing fact and a recommendation if justified. Ask the user, keep that answer pending, and continue independent sections. An unanswered recommendation is not a selected answer.
- Once the user responds, record the answer and its instruction reference, apply it to the exact app/section/locale, handle any newly revealed questions, save within scope and read it back. Reuse the answer on resume unless facts or the user's choice change.
- If an answer conflicts with observed app behavior, explain the mismatch and resolve it before submitting an inaccurate declaration. Do not silently override either the user or the evidence.

Owner-only authentication, identity, payment or agreement actions remain with the owner where required. Prepare known fields and report the exact remaining action; do not turn all technical declarations into owner-only work.

## Save and verify the actual outcome

Follow the Google playbook's edit serialization and publishing controls. Do not mix API and Console writes to the same app concurrently.

1. Read the save/submit control and its surrounding explanation before using it. A questionnaire's Submit action may finalize that declaration; distinguish it from sending the app changes for review or starting a rollout. Use only transitions covered by the user's existing instruction.
2. Save known answers, then reopen the section or use an authoritative readback where supported. Verify selected values, locale/track, validation errors and the displayed saved state. A toast alone is insufficient.
3. Revisit App content, dashboard tasks and Publishing overview after dependent updates. Inspect new questions and pending changes; do not assume an Actioned card means the new release has been approved.
4. Keep `upload_draft` in draft. If the only available save/commit would send changes for review or publish beyond scope, retain the prepared work and explain that concrete transition. Do not invent a universal no-publication switch or add a general approval gate for routine saves already authorized.
5. If review or rollout is authorized, apply the exact intended track/countries/fraction and verify the observed result. Standard publishing may make approved changes live; inspect managed-publishing availability and exceptions before relying on a hold. [Publishing behavior](https://support.google.com/googleplay/android-developer/answer/9859654?hl=en).

Do not erase unrelated pending changes, reset existing signing, activate new monetization, or alter production just to make the dashboard green. Report access or external-review blocks with the next actor/action.

## Keep a section journal

Maintain `release-output/google-sections.md` and link it from STATE.md. Keep it and supporting evidence outside the public preview site. Use secure references for reviewer accounts and redact tokens, credential values, private contact details and sensitive screenshots from shareable evidence.

Record the developer/app/package, source revision, versionCode/track, locale scope, observation time and user's requested destination at the top. Follow the shared workflow's two-table format, populated from the actual Console with no pre-checked rows.

Section coverage:

| Actual section / conditional step | Locale / track / scope | Read time | Disposition and reason | Remaining question / next action |
| --- | --- | --- | --- | --- |
| Populate from live navigation | requested scope | not read | pending | inspect |

Field decisions:

| Section / field | Previous → selected value | Evidence or user-answer reference | User-notification reference | Save/apply outcome | Fresh remote readback / time |
| --- | --- | --- | --- | --- | --- |
| Populate after inspection | unresolved | none | not yet informed | not applied | none |

Keep discovered, visited, saved/verified, unchanged/verified, blocked and not-applicable counts separately. Record why an optional section is not applicable; a section hidden by missing permissions remains blocked, not checked. Retain user answers and their application evidence so resume does not repeat questions or forget to apply them.

## Report completion precisely

Report which sections were reviewed, which choices were applied or retained and why, which user answers were applied, and which items remain unresolved or unread. Tell the user what changed without requiring them to inspect the journal to learn the decisions.

Section coverage is separate from binary/media completion and from Google's approval. Complete inspection can still leave unresolved answers; a completed deployment requires the relevant requested sections to be saved and verified as well as the binary/assets required by the playbook. Missing screenshots cannot be hidden by completed forms, and a successful upload cannot hide an unanswered declaration.

Finish with the section-journal path, actual draft/review/track state, unresolved questions and the exact next actor/action. Do not claim “every section checked” while any discovered section is unread or a conditional branch remains unexplored.
