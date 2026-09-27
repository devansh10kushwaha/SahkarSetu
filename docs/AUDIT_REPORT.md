# SahkarSetu — Audit Report
**Date:** 21 September 2026 · **Build audited:** SIH26089 demo (port 3001) · **Auditor:** Hermes (read-only pass, then fix pass + verification)
**Method:** full source read (2,100 lines Python + 1,100 lines JS), live API probing on an isolated copy, DB invariant sweep, concurrency probes, PDF/rendering inspection, browser journeys (Playwright), and a fresh-clone boot test.

Everything below is either **verified by a run** (command + output) or explicitly marked as *not verified*. No finding is listed on suspicion alone.

---

## 1. Baseline — how it stood before the audit

| Suite | Result before | Notes |
|---|---|---|
| `tests/e2e.py` | 46/46 pass | only covered happy paths |
| `tests/stress.py` | 0 anomalies | invariants held |
| `tests/static_checks.py` | clean | |
| `tests/visual_qa.py` | **crashed** | Chromium needs `--disable-dev-shm-usage --disable-gpu --single-process` on this box; with flags: 20/20 |

The existing suites were green, but they never touched the areas where the real problems were. Each finding below was reproduced with a purpose-built probe first.

---

## 2. Findings

Severity: **S1** = breaks a headline feature / blocks a judge · **S2** = wrong behaviour or data risk · **S3** = quality/hardening.

### S1-1 · Invoice PDF printed no payment breakdown
*The single most important artefact of the pitch — "90/10 printed on every invoice" — was invisible.*

- **Evidence (before):** text extraction of a real invoice showed only `Job charge (visit) Rs 550` clipped at y≈830–845 pt (page is 842 pt tall); "platform fee", "worker receives", the comparison line, the payment reference and the DEMO-MODE banner were all drawn at **negative y** (off-page). Block coordinates confirmed: every breakdown row below 0.
- **Root cause:** `make_invoice_pdf()` reset the cursor with `y = 0` before the totals block, then drew rows downward.
- **Fix:** cursor-based layout from the header down, breakdown always above the footer; PLUS non-Latin support: Helvetica silently renders Devanagari as boxes, so values containing non-Latin text switch to an embedded GNU FreeFont face (plain-English invoices stay 2.6 KB, Hindi invoices ~24 KB).
- **Verified after:** PyMuPDF text + block scan on a fresh invoice → all three breakdown lines present, **0 off-page blocks**; rendered PNG inspected visually (breakdown correct, Hindi address readable, nothing clipped). `tests/e2e.py` now asserts this permanently.

### S1-2 · A fresh clone could not boot
*A judge following the README would see a dead app — three separate defects stacked.*

- **Evidence (before):**
 1. No `data/` dir → `sqlite3.OperationalError: unable to open database file` on `python main.py`.
 2. `python3 -m uvicorn main:app` never ran the seeding code at all (it lived under `if __name__ == "__main__"`), so every request hit "no such table".
 3. When seeding *did* run, `init_db()` ended with `conn.close()` on the **shared** connection — every later query in that process raised `ProgrammingError: Cannot operate on a closed database` (reproduced directly).
- **Fix:** `init_db()` is idempotent, creates `data/` on demand, never closes the shared connection, and runs at import time; schema migrations (`ensure_schema`) run on every boot. New `tests/boot_check.py` copies the app to a scratch dir with no DB and proves boot → seed → login.
- **Verified after:** `BOOT CHECK: 4/4 passed` (boot, catalog, DB created, demo login straight after seeding).

### S2-1 · Passwords: single-round unsalted SHA-256
- **Evidence (before):** `hash_pw()` = one SHA-256 over `"ss$"+pw+"$salt"` with a *constant* string; login compared with `!=` (not constant time) and skipped hashing entirely for unknown phone numbers (timing oracle for user enumeration).
- **Fix:** PBKDF2-SHA256, 210 000 rounds, per-user random salt; constant-time `hmac.compare_digest`; a dummy hash burns identical work for unknown numbers; existing single-round rows upgrade transparently on next successful login.
- **Verified after:** e2e asserts all three demo rows are `pbkdf2_sha256$…` after login; wrong passwords still 401; login costs ~91 ms end-to-end.

### S2-2 · Anonymous visitors could read every worker's phone number
- **Evidence (before):** `GET /api/workers/5` (no auth) returned `"phone": "9826567677"`.
- **Fix:** public profiles mask the number (`98******77`); full numbers remain only for the parties on a booking and for admins.
- **Verified after:** e2e asserts a masked number in the public profile.

### S2-3 · Booking validation gaps
- **Evidence (before):** a booking with `zone: "atlantis"` was accepted and stored as-is; a booking dated `2001-01-01` was accepted; a 200 KB `notes` payload was accepted; worker signup accepted a **1-character password**.
- **Fix:** zone allow-list, schedule window (30 min grace → +90 days), per-field length caps in the Pydantic models, 64 KB request-body cap at middleware level, password minimum on worker signup.
- **Verified after:** e2e asserts 400 / 400 / 413 / 422 / 422 for exactly those five probes.

### S2-4 · Payout run: broken CSV link + silent duplicate payouts
- **Evidence (before):** `/api/a/payouts/run` returned `"csv": "/api/payout_8.csv"` → **404** (the working URL is `/api/a/payouts/csv/8` — the frontend used the correct one, the API contract was wrong). Running the same period again created a second `payout_runs` row (runs 9 *and* 10 for the identical window) — a real double-payment risk against the federation's bank file.
- **Fix:** the returned URL is the working one; a repeated period is refused with 409 unless the caller explicitly passes `confirm_duplicate: true` (the admin UI confirms and retries); period dates are validated; the run row is written inside one transaction.
- **Verified after:** e2e asserts the returned URL downloads (200) and that a duplicate period gets 200 → 409.

### S2-5 · Busy workers were offered jobs they could never accept
- **Evidence (before):** the matcher only excluded busy workers for *emergency* bookings; for normal bookings it could assign a worker who already had an accepted job, and the accept path then refuses ("ek time pe ek hi job") — the booking sat in `requested` forever with no worker recourse (there was no decline).
- **Fix:** the matcher only ever offers **free** verified workers (single query, N+1 removed), and a new `POST /api/w/jobs/{id}/decline` lets a worker hand an offer back: it re-routes to the next nearest free worker, and if nobody is free the booking is cancelled honestly with an explicit note. Declines are recorded per (booking, worker) in a new `declines` table so nobody is re-offered a job he refused.
- **Verified after:** e2e decline flow passes (decline accepted → booking leaves the decliner → second decline rejected).

### S3-1 · Oversized/unbounded rate-limit maps (memory leak) and no IP-wide login cap
- Old `LOGIN_FAILS[key] = recent` left an empty key per phone number forever, and the IP list was unbounded; credential-stuffing across many phone numbers from one IP was unlimited. Fixed: bounded + pruned maps under a lock, plus a 40 fails / 15 min / IP cap.

### S3-2 · Session tokens accepted in the query string everywhere
- `GET /api/me?t=<token>` worked (tokens leak into history/logs). Now the query-string token is accepted **only** by the two browser download endpoints that need it (invoice PDF, payout CSV) — verified: `/api/me?t=` → 401, invoice `?t=` → 200.

### S3-4 · QA suites could "clean" the wrong database (junk in the directory)
- The suites write through two channels at once — the HTTP API (whatever DB the server
  has open) and direct SQLite (`SAHKARSETU_DB`). If those disagree (e.g. a stale env var),
  the run creates rows in the live DB and then purges a different file, reporting success.
- **Evidence:** an accidental leaked `SAHKARSETU_DB` left `QA Tester`, `QA Applicant`,
  `Brute Bait` and `Stress Tester` in the demo directory while every suite said "clean" —
  reproduced and confirmed by direct DB reads; this also exposed that `stress.py` never
  deleted its `Brute Bait` account at all.
- **Fix:** shared `tests/qa_common.py` — every suite prints its resolved `BASE`/`DB`,
  then compares the API's user count (`/api/health`) against the DB file's and **aborts
  with exit 2** on mismatch; `stress.py` now deletes `Brute Bait`; a one-shot
  `tests/purge_junk.py` removes pre-fix leftovers.
- **Verified:** with the stale env var present, e2e now refuses to start (shows the
  mismatch); after `unset`, all suites pass and the live DB returns to exactly 77 users,
  3,810 bookings, integrity ok, zero leftover accounts.

### Smaller correctness items (all fixed)
- `CachedStatic.file_response` read `args[1]` (a `stat_result`) instead of `args[0]` (the path), so its sw.js branch never fired.
- `HEAD /` returned 405 (uptime monitors) → now 200; HTML is `no-cache`, assets `max-age=604800`, `sw.js` never cached (all asserted in e2e).
- Approving *or rejecting* a worker marked all his certificates as co-op verified → certificates are only blessed on approval.
- Multi-step writes (payment, review+aggregate, job completion+`jobs_done`, verification, payout, worker application) ran as separate auto-committed statements → single transaction each (`tx()`).
- `/api/health` added (liveness + DB check) — also the hook for the boot test.
- Cancel now stops after `requested` (unchanged), and a `requested` booking that is declined twice is reported honestly rather than silently.
- Dead code removed (`gen_token_raw`); `sessions` table kept because QA suites reference it.

### 2b. Findings from real use, after the fix pass (21 Sep, same day)

These two were found by using the live deployment, not by reading code — the previous suites were green through both.

**S2-6 · Choosing a worker on his profile silently booked a different one**
- **Evidence:** every booking made from a worker profile was auto-matched instead. The profile endpoint `/api/workers/{id}` returns the key `user_id`, but the profile's Book button built its payload from `w.id` → `undefined` → `JSON.stringify` dropped it → `worker_id` never reached the server:
  `openBooking({"service_id":1})` instead of `{"service_id":1,"worker_id":94}`.
  Confirmed against the DB: four real bookings, **zero** ever carried the chosen worker's id.
- **Fix:** the Book button reads `w.user_id` (with `w.id` fallback) and the profile payload now also exposes `id` (same key as the list endpoint), so the two cannot drift apart again. The booking response's `match_note` also lied ("Nearest free … km away" even when the customer chose) — now "Your chosen worker".
- **Verified:** live browser run — Book button payload `{"service_id":1,"worker_id":94}`, wizard state `worker_id:94`, step-2 label "Your chosen worker", confirmed booking `#3841` landed on worker 94 in the database. Two regression checks added to e2e (70 checks now).

**S2-7 · One ignored offer benched a worker from all future matching**
- **Evidence:** the matcher excluded any worker holding a booking in `('requested','accepted','enroute','in_progress')` — so an *unaccepted* request permanently removed him from the pool (observed live: a booking ignored since 26 Aug had been benching a worker for weeks, and the demo worker was benched by one pending request, which broke the e2e suite's own match assertions). The chosen-worker path, meanwhile, only blocked committed work — the two disagreed.
- **Fix:** committed work (`accepted`/`enroute`/`in_progress`) blocks matching; an unaccepted offer now *holds* a worker only for `OFFER_HOLD_HOURS = 2`, with at most `PENDING_OFFER_CAP = 2` live offers on him at once. Both constants are at the top of the matching section.
- **Verified:** e2e's match assertions pass again and the demo worker receives offers after holding a stale request; suites green (e2e 70/70, visual 20/20, static clean).

**S3-5 · The e2e suite crashed instead of failing**
- When a step upstream failed, the invoice check fed a JSON error body to PyMuPDF and died with `FileDataError`, hiding every later check. Now guarded by a `%PDF` magic-byte check that fails loudly with the payload snippet.

### 2c. Second audit round — decline/expiry, settlement, availability (21 Sep, evening)

Triggered by the worker declining a job and the customer still seeing it as "live". Findings, all fixed and covered by tests:

**S2-8 · A decline was handled correctly but invisibly**
- `decline → re-dispatch to the next nearest free worker` worked, yet the customer's screen just showed a different name with no explanation — the booking looked like it was "still showing" (it *was*, legitimately: it had been re-offered, not cancelled).
- **Fix:** a `booking_events` activity log written on every state change (created / chosen / matched / declined / re-dispatched / accepted / on the way / working / completed / paid / rated / cancelled / expired / no-free-worker), returned by `/api/bookings/mine` and `/api/bookings/{id}`, rendered on the customer's card with IST times ("• declined · Abdullah Worker · 6:28 pm", "• re-sent to Ramesh Kumar · 6:28 pm"). Existing bookings were backfilled from real evidence (decline rows, timestamps) — nothing invented.

**S2-9 · Overlapping payout runs paid the same job twice (money bug)**
- The duplicate guard only compared exact period start/end, and nothing marked a job as settled: running 1–30 Sep and then 15–30 Sep paid the 15–30 jobs again.
- **Fix:** a `payout_items` ledger with `booking_id UNIQUE`; a run only picks jobs that were never in a previous run and records each settlement; the response reports `already_settled_skipped`. Proven on a DB copy (a job cannot be settled twice, an overlapping run pays 0 and reports the skip).

**S2-10 · Nothing showed that a worker was already on a job**
- Picking a busy worker is a hard refusal (his choice is never silently rerouted), but the UI gave no warning and the refusal offered no way forward.
- **Fix:** `busy`/`active_jobs` on the list and profile payloads ("Busy now" badge, "Free now" on the profile), and the refusal now carries the nearest free alternative which the booking sheet turns into a one-tap "Book instead: X (N km)" button.

**S2-11 · Test suites drifted from the live data they run against**
- The e2e fixture assumed the demo worker was always free (he is a working demo account — he was mid-job) and its payout probe ran a **whole-year** period, which with the new ledger would settle the product's entire history. A stale WAL-less DB copy also made one probe read an outdated snapshot.
- **Fix:** the suites now pick a *free* worker they can log into (`worker@2026`/`demo123`) and drive that account, iterate zones to find a drivable match, prove payout on a QA-only future date and delete their own run + settlements, copy `-wal/-shm` alongside the DB, and purge every child table (payments, reviews, events, declines) before deleting bookings — a missing child here is exactly how 4 orphan payments and 81 orphan events appeared.

### Efficiency — measured, not assumed
| Endpoint | Before | After | What changed |
|---|---|---|---|
| `/api/a/overview` | 15.3 ms | **4.7 ms** | 16 queries (each run twice) → 1 query |
| `/api/a/forecast` | 31.5 ms | **9.4 ms** | 110 per-pair COUNTs → 1 grouped query |
| `/api/a/forecast/summary` | 18.7 ms | **1.2 ms** | shares the 30 s model cache instead of recomputing |
| `/api/workers` | 6.8 ms | 3.3 ms | added indexes on hot paths |
| booking match (per request) | N+1 queries | 1 query | `NOT EXISTS` busy filter |
| login | ~0.2 ms | 91 ms | **deliberate**: PBKDF2 210k rounds |

Indexes added: `bookings(worker_id,status)`, `bookings(customer_id,id DESC)`, `bookings(scheduled_for)`, `workers(trade,zone,status)`, `reviews(worker_id)`.

### Test-suite quality (part of "quality")
- Tests no longer hardcode `localhost:3001` or the live DB path — every suite takes `SAHKARSETU_BASE` / `SAHKARSETU_DB`, so QA can run beside the live service without touching it.
- Hardcoded past calendar dates (which only worked while "today" was August) replaced with computed times — the suites no longer rot.
- e2e grew 46 → **68 checks**, including regression checks for every S1/S2 finding; new `boot_check.py` covers the fresh-clone path; `verify_fixes.py` reproduces the invoice + latency evidence.

---

## 3. Verification summary (after)

| Suite | Result after |
|---|---|
| `tests/e2e.py` | **68/68 pass** |
| `tests/stress.py` | 0 api-anomalies, 7/7 DB invariants clean |
| `tests/static_checks.py` | clean (25 handlers wired, i18n complete) |
| `tests/visual_qa.py` | **20/20 pass**, 0 JS console errors |
| `tests/boot_check.py` | **4/4 pass** (fresh clone) |

Concurrency probes that could *not* break the system (kept honest): 8 simultaneous payments on one booking → 1×200 + 7×409; 8 simultaneous accepts by one worker → invariant held (≤1 active job). No exploit was demonstrated; the transaction work above is defence-in-depth, not a fix for a reproduced bug.

---

## 4. Cool features to add (prioritised)

Rating: effort is build time for me; *demo value* is what a judge/federation officer sees in 60 seconds.

| # | Feature | Why it matters | Effort |
|---|---|---|---|
| 1 | **Offer expiry + auto re-dispatch** (offer times out after X minutes → next nearest free worker, customer sees "finding another worker") | Completes the dispatch story; today an ignored offer just sits there | M |
| 2 | **Worker passbook** — monthly earnings statement PDF/CSV per worker with the running 90/10 ledger | The 90/10 promise turned into a document a worker can hold; direct answer to "platform transparency" | S–M |
| 3 | **Audit trail tab** (who verified, paid, ran payouts, changed welfare — immutable log) | Governance credibility for a ministry-facing platform; cheap to build on the `tx()` layer | S–M |
| 4 | **Insurance renewal reminders** (30/7-day alerts + "uncovered workers" export) | Welfare is the PS's heart; proactive beats a static list | S |
| 5 | **Worker digital ID card + QR** (opens the public profile) | Physical-world trust token; worker shows it at a society gate | S |
| 6 | **Forecast → recruitment plan** ("hire ~4 plumbers in Seelampur for Diwali week", one-click notify/CSV) | Turns the AI panel into an action the co-op can execute | S–M |
| 7 | **Dispute / SOS on an active job** → admin queue with both parties' statements | Worker safety and fairness — the gap competitors get criticised for | M |
| 8 | **Match explainability in the customer UI** ("2.1 km, 4.7★, free now" — API already returns it) | Makes the "cooperative algorithm is fair" claim visible instead of asserted | S |
| 9 | **Multi-federation scoping** (federation_admin sees only their co-ops; super_admin sees all) | Required the moment more than one federation is onboarded | M |
| 10 | **Offline booking queue in the PWA** | Field-workers and low-signal areas; the SW exists, this finishes the story | M |

Larger bets if there's appetite: voice-first booking (IVR/voice note) for low-literacy users; UPI-collect integration replacing the mock gateway; Postgres + Redis hardening for a real pilot; SMS/WhatsApp job notifications.

---

## 5. Not fixed (deliberate, documented)

- **Mock payments** stay mock — swapping in a real gateway is a policy/business decision, not a code gap.
- **CSP keeps `'unsafe-inline'`** — the UI uses inline `onclick` handlers throughout; removing it means migrating all handlers to listeners (worth doing before any public launch, not now).
- **Rate limits are in-process** — correct for one uvicorn worker; a multi-worker pilot needs Redis.
- **Shared demo passwords** for the seeded directory remain public by design (they're demo personas).
- **No CSRF token** — the API is bearer-token only (no cookie auth), so CSRF doesn't apply today; revisit if cookie sessions are ever added.

## 6. Rollback & backup

- The pre-audit source was archived before any change; tarball sha256
  `94fac353ed12b4adced593400f933fcf08860bf59afd05db99ce26c7919da684`, with the
  pre-migration database snapshot kept alongside it.
- The demo deployment runs as a systemd service on port 5001
  (`https://jr29e-5001.aiccloud.online/`). Restore = untar the archived copy over the
  service directory and restart the unit.
- The pre-audit baseline copy was removed after this report; the tarball above is the
  byte-exact pre-audit source, and the "before" evidence is captured in §2 and §3.
