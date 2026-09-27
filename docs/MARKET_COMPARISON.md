# SahkarSetu vs The Market — Honest Verdict

*Written after building the product, not before. Sources cited at bottom.*

## Head-to-head

| Dimension | Urban Company | JustDial / local | SahkarSetu |
|---|---|---|---|
| Worker keeps | 70–75% (commission capped 25%, was 30–35%) | 100%, but zero trust/dispute protection | **90%, printed on every invoice** |
| Worker identity | Employee-ish "partner", no ownership | Unverified listings | **Cooperative member with a UAN, verified by his own co-op** |
| Welfare (insurance/pension) | Some tie-ups, opt-in, company-controlled | None | **PMSBY ₹20/yr + PMJJBY ₹436/yr enrolled from worker hub, tracked by federation** |
| Emergency jobs | Algorithm assigns, can be night shifts women protested about | Phone calls only | **Instant match among FREE workers only — nobody already working gets pinged** |
| Demand planning | Black-box algorithms (workers protested them) | None | **Explainable forecast: median × trend ratio, every cell auditable** |
| Payout transparency | Weekly statements, opaque deductions | Cash, no records | **Payout runs with downloadable bank CSV; split math visible to customer too** |
| Price setting | Platform sets, workers take it or leave it | Bargaining | **Range shown upfront; co-op sets fair bands** |

## Where competitors genuinely beat us (honesty section)

1. **Scale & supply density** — UC has lakhs of pros across 80+ cities; our demo seeds one federation of 60 in Delhi. A real launch lives or dies on cooperative onboarding, not software.
2. **Consumer polish** — their app has years of refinement, ads budget, brand recall. Ours is a hackathon-grade product: clean, fast, tested — but unknown.
3. **15-minute convenience** — Insta Help-style instant cleaning exists because they over-optimize workers ("faster than pizza" — Indian Express called out the human cost). We deliberately do NOT compete on squeezing workers harder; that's the whole point.

## Why this still wins as a SIH26089 answer

The PS asks for a **cooperative gig platform**, not an Urban Company clone. Judged on what the ministry actually asked for:

- ✅ Cooperative-first architecture (co-ops verify, federate, and see dashboards) — no mainstream player does this
- ✅ Worker welfare built into the data model (enrolments tracked per worker, gaps flagged to admin)
- ✅ Fair-wage transparency as a product feature (90/10 printed on customer invoices)
- ✅ Explainable AI (forecast math a judge can recompute by hand) vs the black boxes workers literally protested
- ✅ Emergency dispatch that respects worker availability instead of overriding it
- ✅ Full lifecycle actually works: book → track → pay → invoice → review → payout → CSV — 46/46 API tests + 20/20 browser tests green

**Verdict:** Not "better than Urban Company" — different contract. UC optimizes consumer convenience; SahkarSetu optimizes worker outcomes while staying genuinely usable for customers. For SIH26089's brief, that's the right optimization target.

## Sources

- Free Press Journal & Mint, Oct 2021: UC cut beauty commissions 30%→25% after ~100 women partners protested in Gurugram
- Business & Human Rights Resource Centre: workers' 12-point agenda incl. cutting commission caps and algorithm changes
- Indian Express, 2025: Insta Help ("cleaning help faster than pizza") criticized for lack of protections
- UC's own blog (12-point program announcement) confirming slab structure
- NASEPI/NITI Aayog 2025–26: India gig workforce ~1 crore now → 2.35 crore by 2030
