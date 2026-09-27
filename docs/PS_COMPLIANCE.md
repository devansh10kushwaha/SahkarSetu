# SIH26089 — Problem-Statement Compliance Matrix

**Problem statement (Ministry of Cooperation / NCCT):** *"To develop a cooperative-owned
digital service marketplace platform that enables Labour Cooperative Federations and Labour
Cooperative Societies to provide verified household and community services while ensuring
fair wages, worker welfare, and consumer trust."*

Every row below is **proven against the running build** by `tests/ps_compliance.py`
(26 checks, 0 mocks — real API calls + SQL assertions on the live database).
Run it yourself:

```bash
SAHKARSETU_BASE=http://127.0.0.1:3001 python3 tests/ps_compliance.py
```

| # | Expected solution feature (PS wording) | How SahkarSetu does it | Proven by |
|---|----------------------------------------|------------------------|-----------|
| 1 | Service provider registration and verification | Worker self-applies (`/api/apply-worker`) into a cooperative → `workers.status='pending'`, invisible to customers → federation/society approves (`/api/a/verify/{id}`, `/api/c/verify/{id}`) → verified badge + bookable | registration → pending → not publicly listed → queue → verified → listed |
| 2 | Worker skill profiling and certification | Skill level computed from experience + cooperative-VERIFIED certificates + rating (`expert/skilled/helper`); worker adds his own certificates (`/api/w/certs`), a society blesses each one (`/api/c/certs/{id}`); only verified certs show on the public profile | profile exposes `skill_level`; cert pending → verified via society; profile reflects it |
| 3 | Customer booking and scheduling system | Two-step booking wizard with **real date + time picker** (ASAP / tomorrow 10 AM / custom slot), server-side bounds: no past, ≤ 90 days | booking at +3 days 15:30 succeeds; past → 400; +120 days → 400 |
| 4 | Geo-location based service matching | Haversine matcher over verified free workers with an explainable score (distance −0.9/km, rating +0.35, today's jobs −0.6); Leaflet/OSM map with pins | worker pins present; booking response carries `distance_km` + `match_note` ("Matched plumber — 1.2 km · ★4.7 · 0 jobs today") |
| 5 | Digital payments and invoicing | Demo UPI gateway (`DEMOUPI…` refs), **90/10 split enforced in the ledger**, printable PDF invoice that prints the split | payment records `worker_net + commission == amount`; invoice.pdf renders (PyMuPDF text contains "platform fee (10%)") |
| 6 | Rating and feedback mechanism | One review per completed booking (409 on duplicate), worker `rating_avg`/`rating_count` updated transactionally | review ok; second → 409; rating_count +1 |
| 7 | Worker welfare and insurance integration | Worker applies for PMSBY/PMJJBY himself → society/federation approves → cover active with validity window; insurance **claim** can be filed and decided; e-Shram UAN linked on the record | apply → pending → approve → active (valid_till); claim filed → approved; UAN present |
| 8 | Emergency and on-demand service booking | Emergency flag on the booking; instant match to a free worker in the same response, `is_emergency` stored and surfaced (bolt badge) | emergency booking returns an assigned worker + readable match reason |
| 9 | Cooperative federation administration dashboard | Federation dashboard (overview, verification queue, certificates, payouts + CSV, welfare centre, allocation board, demand forecast) **plus a society-level dashboard** hard-scoped to one cooperative (`/api/c/home`), with role separation | dashboard stats keys; society counts == DB counts for that coop; customer token → 403 on both |
| 10 | Multilingual mobile application | Installable PWA (manifest + service worker + offline page) with Hindi / English / Urdu packs and RTL for Urdu | manifest + offline.html served; 36 translated string groups; RTL switch in i18n.js |
| 11 | AI-based demand forecasting and workforce allocation | Explainable forecast (day-of-week median × 14-day trend, 7-day zone×trade grid) feeding an **allocation board** that pairs forecast demand with verified supply and prints the action ("central: no verified caregiver — recruit now") | 385 forecast rows over 7 days; 55 allocation rows each with severity + action |
| — | Cooperative-owned (background paragraph) | Federations → cooperatives → workers; every worker carries his samiti; society admins manage their own members; platform fee fixed 10% | society scoping checks; payout ledger; invoice split |
| — | Technology components | Mobile Applications (PWA), AI (forecast + scored allocation), Geo-Spatial (Haversine + OSM/Leaflet), Digital Payments (demo UPI + PDF invoice), Cloud (systemd service, `0.0.0.0` bind, public door) | `/api/health`, live URL, tests above |

## Demo accounts (demo build)

| Role | Phone | Password |
|------|-------|----------|
| Customer | 9000000001 | demo123 |
| Worker (electrician, Seelampur) | 8000000001 | demo123 |
| Federation admin | 7000000001 | admin123 |
| Society admin (Seelampur samiti) | 7000000101 | admin123 |
| Society admin (Mayur Vihar samiti) | 7000000102 | admin123 |

## Honest limitations (say these before a judge asks)

- Payments are a **demo gateway** — no real UPI/PSP integration; the split ledger is real, the money is not.
- Welfare records are **demo records**; PMSBY/PMJJBY enrolment and claims are modelled, not filed with the insurers.
- The "mobile application" is an **installable PWA**, not a Play Store artefact.
- Forecast and allocation are **explainable statistical/heuristic models**, not trained ML — deliberate, so a judge can verify the logic on one slide.
- Notifications are in-app only (activity log); no SMS/WhatsApp/push yet.
