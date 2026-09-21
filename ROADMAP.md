# DineFlow Platform Roadmap

*Draft v2 · 2026-09-19 · living document — update it as decisions land.*

**Contents:** 1 Goal · 2 Build order · 3 Decisions · 4 Today · 5 Stages · 6 Feature catalog · 7 Design notes (tenancy, flags, theming, **QR table ordering**, **kitchen screen**, smart features) · 8 Not now · 9 Risks · 10 Gates · 11 Next two weeks · 12 Assumptions

---

## 1. Goal

Turn DineFlow from one restaurant's app into a **platform**: create a branded restaurant site for a
client in minutes from one codebase, ship new features safely behind flags, then hand the client
their admin login. Build the plumbing once; every new client is configuration, not code.

**Principles**

1. **Config over code.** A client's site is *rendered from data*. We never generate or fork code per client.
2. **One deployment, many tenants.** No per-tenant builds. Tenant is resolved per request.
3. **Ship dark, release gradually.** New features land behind flags, on for our own demo tenant first.
4. **The server is the authority.** Hiding a button is not access control. Tenancy, flags and permissions are enforced in the API.
5. **Buy commodity, build differentiators.** Payments, email, SMS, storage, error tracking are bought. QR table ordering + live kitchen + reservations + floor plan in one system is what we build.

## 2. Build order — decided

There is no client yet, so the goal is *a running app that demos well*. The order that gets there without expensive rework:

| Stage | What | Why now |
|---|---|---|
| **A. Thin foundation** (timeboxed) | Hardening, tenant isolation, per-tenant URLs/customers, real-time + storage + jobs + email, minimal feature flags | Only things that are **expensive to retrofit**. Every later feature builds on them, and **printed QR codes can't change URL scheme later**. |
| **A½. Demo kit** (~1 week) | `create-tenant` script + logo/primary-color theming | Prospects react to *their own* logo and colors. A script is enough; no console yet. |
| **B. Hero experience** | **QR table ordering, table sessions, live kitchen screen, waiter alerts, pay at table, guest checkout** | This is what sells. Built tenant-aware and flag-gated from the first commit. |
| **C. Reservations 2.0 & guest CRM** | Waitlist, reminders, deposits, pacing, table combining, hours enforcement | Turns the existing reservation engine into a full front-of-house tool. |
| **D. Growth features** | Loyalty, reviews, coupons, scheduling, analytics 2.0, languages, smart features | Retention and upsell; ship one flag at a time. |
| **E. SaaS shell** | Platform console, onboarding wizard, full branding engine, custom domains, billing | No data-model impact, so it's cheap to add **when you have a client to onboard**. |

**Why not "features first, SaaS last"?** Tenancy touches every table, query, login, upload path, job and
webhook. Retrofitting after building QR ordering, real-time kitchen, notifications and Stripe means
reopening and re-testing all of it, and fixing already-printed QR links. **Why not "SaaS first"?**
You'd spend weeks on consoles and wizards with nothing to demo. The thin-foundation path keeps the
risky rework out and the demo close.

**Keep Stage A honest:** it is *only* the list in §5. If a task isn't expensive to retrofit, it waits for Stage E.

## 3. Decisions to lock first

| # | Decision | Recommendation |
|---|----------|----------------|
| D1 | What does "hand over" mean? | **Hosted multi-tenant**: client gets admin login + domain; you operate it. Code handover only as a premium single-tenant option, plus data export on exit. |
| D2 | What is a tenant? | **Restaurant = tenant** now. Add an Organization (multi-location) only when asked; keep ids additive. |
| D3 | Isolation | **Shared DB + `tenant_id` + Postgres row-level security.** |
| D4 | Tenant resolution | **Host header at runtime**: `{slug}.yourplatform.com` first, custom domain later. |
| D5 | Customer accounts | **Per tenant** (`unique(tenant_id, email)`); staff keep memberships; platform staff are a separate role. Guests can order without an account. |
| D6 | Feature flags | **Build a minimal one** (two kinds, §7.2). |
| D7 | Payments | **Stripe Connect**: the restaurant is the merchant. |
| D8 | Real-time transport | **Server-Sent Events** first (simple, proxy-friendly, one-way is enough for kitchen/guest updates); WebSockets only if needed. |
| D9 | QR access policy (default) | **Table must be seated/occupied** before QR ordering opens; per-tenant setting to allow open / PIN / staff-approved (§7.4). |
| D10 | QR link shape | `https://{tenant-host}/t/{opaque-token}` — token is random and **rotatable**, never the table id. Decide now: it gets printed. |

## 4. Where we are today

**Reusable:** `restaurant_id` on most tables · staff↔restaurant membership + access checks · brand colors already CSS variables wired into Tailwind · `logo_url`, opening hours, tax, fees on `Restaurant` · reservation engine (status, buffer, overstay), floor plan editor and seating plan · kitchen board (polling) · analytics · CI, Docker, migrations, tests.

**Gaps (verified in code)**
| Area | Today | Needed |
|------|-------|--------|
| Tenant resolution | Default slug **baked in at build time**; admin store picks the first restaurant | Resolve by Host per request |
| Users | `users.email` **globally unique** | Per-tenant customers, tenant claim in JWT |
| CORS | Static env list | Dynamic per tenant domain |
| Uploads | Local disk, menu images only | Object storage + image pipeline |
| Feature flags | None | §7.2 |
| Email / SMS / jobs / real-time | None (kitchen polls every 15 s) | Email, SMS, job queue, SSE |
| Payments | Mock only | Stripe Connect |
| Sessions | ~~30-min token, refresh never used~~ — **fixed**: silent refresh with single-flight + multi-tab safety | — |
| Orders | Login required; no table sessions; one order per reservation | Guest orders, table sessions, rounds |
| Platform admin | `SUPER_ADMIN` role, no UI | Console (Stage E) |

**Known issues (status):** ~~client-supplied order `discount`~~ fixed · ~~no rate limiting~~ fixed · admin test coverage restored in `tests/test_admin_management.py` (your working copy of `test_admin.py` is still trimmed — decide whether to keep or restore it).

## 5. Stages

Estimates are **rough, one focused full-time developer**; double for part-time.

### Stage A — Thin foundation · ~6–9 weeks
**A1 Hardening (1–2 wk)**
- [x] Server-side order pricing; remove client `discount` (and client `table_id`).
- [x] Silent token refresh; rate limiting; password rules; security headers (API and site).
- [x] Restore/extend tests (new admin suite found and fixed 3 crash bugs). [ ] Make CI required on `main` (GitHub branch-protection setting — do this in the repo settings).
- [x] Error tracking hook (Sentry, optional), structured JSON logs + request ids, readiness check, DB backup scripts with a **verified restore drill** (`docs/OPERATIONS.md`). [ ] Staging environment; off-site backup schedule.

**A2 Platform plumbing (2–3 wk)**
- [x] Object storage (local or any S3-compatible) + image validation, resize, WebP, thumbnails, metadata stripping; per-tenant prefixes and cleanup; logo upload.
- [x] Transactional email (SMTP/console backends, branded HTML+text templates, escaping) and a **Postgres-backed job runner** (transactional enqueue, SKIP LOCKED, retries with backoff, crash recovery, NOTIFY wake-up). First uses: order confirmation, reservation confirmed/cancelled.
- [x] **SSE real-time channel** with per-tenant topics — Postgres `LISTEN/NOTIFY` fan-out (works across workers, delivers only on commit), fetch-based client with reconnect/watchdog. **Kitchen screen is live** (315 ms order → screen in a 2-worker test). Next: reuse it for guests, waiters and the floor view.

**A3 Multi-tenant core (3–4 wk)**
- [x] Schema audit + expand/contract migration `0006`: customers belong to a restaurant (`users.restaurant_id`, per-tenant unique email), `custom_domain`, per-tenant order-number counters; Bella Vista is tenant #1.
- [x] Tenant from the Host (`<slug>.PLATFORM_DOMAIN`, custom domains, dev fallback) via `GET /tenant`; **tenant claim in the JWT**, checked on every request; customers cannot act in another restaurant; `/restaurants` directory is platform-admin only; `/auth/my-restaurants` for staff; per-tenant sequential order numbers (`BV-1001`); dynamic CORS.
- [x] Frontend bootstrap: tenant from the address in SSR, baked-in slug removed, clear "no restaurant here" page, restaurant-scoped sign-in/sign-up. Also upgraded pinia 2→3 (2.x crashed SSR on any error page).
- [x] **Isolation test suite** (`backend/tests/test_tenant_isolation.py`): every route must be classified, every `/admin` route swept with wrong-tenant/staff/customer tokens, IDOR table, customer attacks, and a full-data snapshot proving nothing changed.
- [ ] **Row-level security** as a second net: needs a non-superuser app DB role (the current `dineflow` role bypasses RLS), `SET LOCAL app.tenant_id` per request, and explicit bypass for trusted jobs. Do before the first real client.
- [x] Fixed: signed-in page loads no longer mismatch between server and browser in the site header, the admin sidebar and the profile page (they used to keep the server's link targets under the wrong labels). Other pages that read browser-only state directly may still warn; use `useHydrated()`.

- [x] **Password reset and change**: emailed one-time links (hashed, 1 hour, single use, throttled), same answer whether or not the account exists, all other sessions signed out on any change, notification email, change-password while signed in.

**A4 Minimal feature flags (~1 wk)**
- [x] Code-declared registry (`app/core/features.py`) + per-restaurant DB overrides; server-enforced `requires_feature(...)` (staff routes) / `FeatureService.require` (customer routes); flags delivered with `GET /tenant` and read with `useFeature()` on the frontend; audit log of every change. First gated feature: `reservations`. Operate with `python -m app.cli` or the `/platform` API (platform admins only); a UI can come later.

**Exit:** two seeded tenants on one deployment; isolation suite green; Bella Vista unchanged; a flag can turn a module off for one tenant in the API *and* UI.

### Stage A½ — Demo kit · ~1 week
- [x] `python -m app.cli create-tenant`: name, slug, logo, brand colour, cuisine template (generic / pizzeria / cafe: starter menu, tables, hours), owner admin account; switches on `custom_branding`; audited. Prints the site address and a one-time password.
- [x] Palette generated from one colour with a contrast check (brand-600 is darkened just enough for white text to reach WCAG AA); CSS variables, page title and favicon rendered on the server, so there is no flash of the default theme. Only when the restaurant's `custom_branding` flag is on. Logo shown in the header.
- [x] Owner invite: no password is ever printed; `create-tenant` produces a one-time set-password link (optionally emailed). Password reset, reset-by-email and change-password are built (see A1/A3 hardening).
- [ ] Not yet: a settings-page colour picker and logo uploader, branding on the admin area and emails.
- **Exit:** ~10 minutes from nothing to a prospect's site with *their* name, logo and colours. Try it: `docker compose exec backend python -m app.cli create-tenant --name "Luigi's" --slug luigis --owner owner@luigis.demo --color "#c0392b" --template pizzeria`.

### Stage B — Hero experience · ~8–12 weeks
Build order matters; each step is flag-gated (`qr_ordering`, `kds_v2`, `pay_at_table`…).

**B1 Table sessions & QR (2–3 wk)** — §7.4 · *first slice built, flag `qr_table_ordering`*
- [x] Table QR tokens (random, rotatable, replaced when a tab closes); printable branded table tents (browser print, one card per table); "Replace code" per table.
- [x] Table sessions (one shared tab per table, race-safe), guests join by scanning, each device holds a table pass that is not a login.
- [x] Live status for guests (and for customers on their order page) over SSE, with a slow poll only as a fallback.
- [x] Guest ordering without an account; multiple rounds (each appears on the kitchen screen as "table N"); retry-safe sends (`Idempotency-Key`); refused rounds leave nothing behind; max round value.
- [x] Access policy: seated-only (default) or open, per restaurant (`restaurants.qr_access_policy`).
- [x] Call waiter / ask for the bill from the table (one open request per kind, live to staff with a nav badge, cleared when staff answer or the tab closes).
- [ ] Still to do in B1: PIN and staff-approved policies (no admin setting for the policy yet), table moved/merged mid-session, PDF/PNG tent export, QR ordering inside opening hours, station routing.

**B2 Live kitchen screen v2 (2–3 wk)** — §7.5 · *first slice built*
- [x] Real-time tickets (SSE), stations (Kitchen / Bar / Dessert; each dish has a station, each screen shows only its own dishes), timers with amber (8 min) and red (15 min) escalation, oldest first, sound on a new ticket (toggle, remembered), full-screen button; a screen remembers its station.
- [x] Item-level status: tap a dish to bump it, tap again to recall; the order turns PREPARING/READY on its own as dishes are bumped (customers and guests follow it live); "Bump all"; "Served — clear".
- [x] Notes and options in bold; **86** a dish live from the "Still to make" all-day counts (gone from every menu and QR ordering at once, with a Bring back list); all-day counts.
- [ ] Still to do in B2: per-tenant custom stations and thresholds, course firing, a wall-mounted "expo" view (ready-to-pass across stations), sound choices, allergen tags on dishes, kitchen stats (average ticket time).

**B3 Front of house (1–2 wk)**
- [x] Guest phone shows live status (Received → Preparing → Ready/Served). *(done in B1)*
- [x] **Service requests**: call waiter, request bill → staff queue and badge. *(done in B1; water/napkins and sound alerts still to do)*
- [x] **Waiter view** (`/admin/waiter`): live floor plan with each table's tab total, tables that need someone (requests, food ready to serve) glowing and queued longest-waiting first; tap a table for its rounds, mark rounds served, answer requests, **add items on the table's behalf**, **move the tab to another table** (kitchen, requests and guests follow; old table to cleaning, its QR replaced), close the tab. Seat walk-ins.
- [ ] Still to do in B3: merge tables, void/comp with a reason, split-the-tab views, per-waiter sections, a sound for new requests.

**B4 Pay at table (2–3 wk)**
- [ ] Stripe Connect onboarding per tenant; pay the full bill, split equally or by item; tips; Apple/Google Pay; receipts by email.
- [ ] "Pay at counter / cash" request → staff marks paid; closing the session frees the table (→ cleaning) and **rotates the QR token**.

**B5 Hours & basics (1–2 wk)**
- [ ] Tenant timezone; opening hours by weekday/shift; holidays and closures enforced on orders and reservations.
- [ ] Notifications: booking confirmation/reminder, order status (email first).

**Exit — Demo milestone:** scan a table QR on a phone → order → the kitchen screen lights up with "T5" → status updates on the phone → request the bill → pay → table flips to cleaning. Repeatable on a demo tenant.

### Stage C — Reservations 2.0 & guest CRM · ~4–6 weeks
- [ ] Confirm/cancel links in reminders; deposits / no-show fee (Stripe); auto no-show release.
- [ ] Waitlist & walk-in queue with SMS "your table is ready".
- [ ] Pacing (max covers per 15-min slot), per-tenant party limits and lead time, blackout dates.
- [ ] Table combining for large parties; smarter auto-assignment (least wasted seats).
- [ ] Guest profiles (visits, spend, notes, allergies, VIP tags), calendar view, embeddable booking widget.

### Stage D — Growth features · ongoing, one flag at a time
Loyalty · reviews · coupons/gift cards · scheduled pickup slots · delivery zones/fees · order throttling when busy · analytics 2.0 · multi-language · web push · smart features (§7.6).

### Stage E — SaaS shell · ~6–8 weeks, when a client is ready
- [ ] Platform console: tenants, status, health, impersonate (audited), flag UI.
- [ ] Onboarding wizard with live preview → owner invite → handover checklist; tenant lifecycle `draft → preview → live → suspended → archived`.
- [ ] Full branding engine: fonts, radius, hero, 2–3 templates, reorderable sections, branded emails, Open Graph.
- [ ] Custom domains: DNS verification + automatic TLS.
- [ ] Billing (Stripe Billing or invoices), plans ↔ entitlements, terms/privacy, GDPR export/delete, status page, data export on exit.

## 6. Feature catalog

**Tier:** **M** must-have to sell · **S** should-have · **N** nice-to-have. **Stage** in brackets.

### QR & dine-in
- **M** Table QR → menu → order to that table [B1] · guest ordering, no account [B1] · multiple rounds & shared table session [B1]
- **M** Live order status on the guest's phone [B3] · call waiter / request bill [B3] · pay at table, split, tip [B4]
- **S** Staff-approve or PIN modes [B1] · printable QR tents with branding [B1] · order on behalf of guests [B3] · table transfer/merge [B3]
- **N** Item-level split, group ordering ("who ordered what") [D] · re-order last visit [D]

### Kitchen & bar
- **M** Real-time tickets, no refresh [B2] · timers/urgency, bump, sound [B2] · notes & allergens highlighted [B2]
- **S** Stations and routing by category [B2] · 86 an item live [B2] · all-day counts, recall [B2] · course firing (starters → mains) [D] · expo screen [D]
- **N** Printer fallback [D] · PIN quick-switch on shared tablet [D] · offline-tolerant PWA [D]

### Reservations & waitlist
- **M** (done) availability, holds, seating, floor plan, overstay handling
- **M** Opening hours/timezone enforcement [B5] · reminders with confirm/cancel [C]
- **S** Waitlist + SMS [C] · deposits & no-show fees [C] · pacing/covers per slot [C] · table combining [C] · guest notes/tags [C]
- **N** Embeddable widget [C] · private dining/events [D] · Reserve-with-Google [D]

### Ordering (online)
- **M** Real payments (Stripe Connect) [B4] · guest checkout [B1/B5] · order notifications [B5]
- **S** Scheduled pickup slots [D] · delivery zones/fees [D] · coupons & gift cards [D] · pause ordering when busy [D] · service charge/tips [B4]
- **N** Delivery driver tracking [later] · aggregator integrations [later]

### Menu
- **M** (done) categories, modifiers, photos, availability
- **S** Allergen/dietary tags + filters [B2/D] · time-based menus (lunch/dinner), happy-hour pricing [D] · stock counts & low-stock alerts [D]
- **N** Bulk import (CSV) [D] · AI-written descriptions [D] · upsell suggestions [D]

### Staff & operations
- **M** Roles: owner, manager, host, waiter, kitchen [A/B] · staff invites [B]
- **S** Assign waiters to sections [B3] · audit log [A4] · end-of-day report [D]
- **N** Shifts/scheduling, tip pooling [later]

### Guests & retention
- **S** Receipts by email [B4] · reviews after visit [D] · saved details/favorites [D]
- **N** Loyalty points [D] · birthday offers [D] · campaigns (email/SMS) [later]

### Analytics
- **S** Sales by hour/day/item, table turn time, average dining duration, no-show rate [D] · exports (CSV) [D]
- **N** Forecasting, staff performance, benchmark vs last month [D]

### Smart features (see §7.6)
Turn-time prediction · best-fit table suggestions · overstay/late-arrival prompts (partly done) · prep-time ETA · no-show risk · upsell suggestions · low-stock alerts · review summaries [D]

### Platform / SaaS
Multi-tenant [A] · feature flags [A4/E] · branding [A½/E] · console & wizard [E] · custom domains [E] · billing [E] · public API + webhooks [D/E] · i18n [D] · PWA [D]

## 7. Design notes

### 7.1 Tenancy
- Resolve tenant from `Host` → tenant row (cached); sign tokens with `tenant_id` and reject mismatches.
- Every query goes through a tenant-scoped repository; **RLS is the second lock**, not the first.
- Slugs double as subdomains: reserve `www`, `admin`, `api`, `app`, `static`, `mail`.
- **Expand/contract migrations** (add nullable → backfill → enforce) so old and new code coexist during a release.
- Background jobs, SSE topics, file paths and Stripe webhooks all carry the tenant id.

### 7.2 Feature flags — two different things
| | Entitlement | Release flag |
|---|---|---|
| Question | "Did this tenant enable/buy this module?" | "Is this new code safe to show yet?" |
| Lifetime | Permanent | **Temporary** — delete after rollout |
| Example | `reservations`, `qr_ordering`, `sms` | `kds_v2`, `new_checkout` |

- Flags are **declared in code** (name, default, owner, expiry); the DB stores only overrides.
- Evaluated **server-side**; the frontend gets the resolved set in SSR tenant config.
- Kill switch + audit trail per flag; **expired flags fail CI** until removed.
- Never gate a destructive migration behind a flag: migrate first, flag behavior after.
- **Rollout ladder:** demo tenant → 1–2 friendly tenants → 10% → 100% → delete the flag.

### 7.3 Theming
- Client gives: name, logo(s), **one primary color**, optional accent, a font pair from a curated list, radius, hero image, tagline, socials.
- We *derive* the 50–900 scale and surface/ink colors and **validate contrast (WCAG AA)** so clients can't make unreadable buttons. Locked: layout, spacing, accessibility. Flexible: color, type, imagery, section order.
- Injected server-side as `:root` CSS variables (already the shape of `main.css`) plus title, favicon, OG image, theme-color.
- Keep templates to 2–3: each one multiplies testing.

### 7.4 QR table ordering — the flow
1. **Setup:** every table gets a random, rotatable **QR token**. Print branded tent cards per table. Link = `https://{tenant-host}/t/{token}`.
2. **Scan:** the site resolves tenant (Host) and table (token) → opens the tenant's branded menu with "Table 5" locked in. No login.
3. **Session:** scanning creates or joins the table's **session** (a shared tab). Everyone at the table sees the same running order and total. Cookies identify each device.
4. **Order:** browse (dietary filters, photos) → add items, modifiers, notes → **Send to kitchen**. Each send is a **round**; items route to stations (kitchen/bar).
5. **Kitchen:** ticket appears instantly: *T5 · Round 2 · 3 items · 0:00*. Status changes stream back to the guest's phone.
6. **Service:** guests tap *Call waiter / Request bill*; waiters see requests on the floor view.
7. **Pay:** the guest pays all, splits equally or by item (with tip), or asks to pay at the counter; staff can mark cash/card.
8. **Close:** paying closes the session → table goes to **cleaning** and the **QR token rotates**, so an old photo of the QR is useless.

**Abuse control** (someone can photograph a QR and order remotely): default policy is that **ordering opens only when the table is seated/occupied** (tie-in with the existing reservation/seating state). Alternatives per tenant: staff approves the first order, a 4-digit PIN printed on the tent, or fully open. Add rate limits, a max order value, and rotate the token on close.

**Edge cases to handle:** item sold out mid-order · kitchen closed/out of hours · duplicate taps · flaky connection (retry-safe requests) · guest switches phones · table moved/merged mid-session · partial payment failure · refund/comp after payment.

**Data sketch:** `table_qr_tokens` · `table_sessions` (tenant, table, state, opened/closed) · `orders.table_session_id` and `round_no` · `order_items.station` and `status` · `service_requests` · `payments.table_session_id` · `session_guests`.

### 7.5 Kitchen screen v2
Real-time over SSE (no polling) · one screen per **station** · tickets sorted oldest-first with **color escalation** (e.g. amber at 8 min, red at 15) · bump/recall · sound on new ticket · allergens and notes in bold · "86" removes an item from all menus and QR ordering instantly · all-day counts ("6× margherita open") · course firing later · works full-screen on a cheap tablet, reconnects automatically after a dropped connection.

### 7.6 "Smart" features — grounded, not hype
Start **rule-based**, then improve with the data you collect:
- **Turn-time prediction:** average dining duration by party size/day → suggest default booking length.
- **Best-fit tables:** pick the smallest free table that fits; suggest combining tables for big parties.
- **Prep-time ETA** per order from recent ticket times, shown to guests.
- **No-show risk:** simple score from history (first-time, no confirmation, long lead time) → nudge reminders/deposits.
- **Overstay/late prompts:** (overstay handling already built) extend to "next party is waiting" alerts.
- **Upsell:** "often ordered together" from order history; low-stock and 86 suggestions.
- **Later, with an LLM:** menu descriptions, review summaries, natural-language analytics ("how did Friday do?").

## 8. What *not* to build yet
Drag-and-drop page builder · per-client code generation/deployments · native mobile apps · multi-location organizations · your own payment processing / email server / flag service · delivery-driver logistics · a marketplace.

## 9. Risks
| Risk | Mitigation |
|------|------------|
| **Platform built with no customers** | Keep Stage A thin and timeboxed; the demo milestone (end of B) is the target; line up first prospects during B. |
| Cross-tenant data leak | RLS + scoped repos + isolation suite in CI; security review before the 2nd real tenant. |
| QR ordering abuse / prank orders | Seated-only default, PIN/approval modes, rate limits, token rotation. |
| Real-time complexity | SSE first, retry-safe endpoints, reconnect + catch-up on the client. |
| Restaurants are price-sensitive and churn | Setup fee + monthly; pick a niche where you are clearly better. |
| You become the ops team | Backups, monitoring, status page, boring infrastructure. |
| Payment liability | Stripe Connect; card data never touches you. |
| Flag sprawl | Owners, expiry, CI failure on expired flags. |
| Scope creep | §8 list; new ideas go to the catalog, tier-tagged, before they enter a stage. |

## 10. Go / no-go gates
- **Before Stage A:** D1–D10 signed off; pick a niche (region/cuisine) and jot down who the first 5 prospects could be.
- **End of A:** isolation suite green; backup restore drilled; staging up.
- **End of B (demo milestone):** run the full QR flow on a real phone in a real venue-like setup; **start showing it to prospects now**.
- **Before Stage E:** at least 1 client (or paid design partner) waiting to be onboarded.
- **Before public launch:** payments tested end to end, legal pages live, on-call plan for peak hours.

## 11. Next two weeks
1. Sign off D1–D10 (edit this file). Pick the niche.
2. **A1:** server-side pricing (remove `discount`), silent token refresh, rate limiting, restore admin tests, CI required.
3. **A1:** Sentry, staging environment, backup + restore drill.
4. Write the **isolation test skeleton first** (tests before the `tenant_id` migration).
5. **Spike (1–2 days):** Host-based tenant resolution in Nuxt SSR and injecting CSS variables for a hard-coded second theme. De-risks A3 and the demo kit early.
6. **Spike (1 day):** SSE endpoint + a kitchen page that updates without polling.

## 12. Assumptions
- One developer; estimates are ranges, not promises.
- Stack stays Nuxt + FastAPI + PostgreSQL + Docker.
- Hosted multi-tenant (D1). The client owns their brand and content; you own the platform code (put this in the contract).
- The target niche is not chosen yet — the largest open question.
