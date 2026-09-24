# Vero.ai — Vero Cloud Pricing Model

**Status:** Phase 14 deliverable. A real, source-cited cost model for the Vero Cloud plan, calculated from Phase 13's actual (CPU-only, direct-RTSP) architecture — not a final, locked, customer-facing price. See "What this document does not do" below.

**Scope:** Vero Cloud only. Own Hardware's price is a market-positioning choice (PROJECT.md: "significantly lower monthly price"), not cost-derived, and is out of scope for this phase.

## Method

`docs/PROJECT.md` names the inputs: "GPU/CPU compute, camera count/resolution/FPS, bandwidth, database, storage, monitoring, payment fees, operating overhead, and profit margin." The model turns those into a single number in five steps:

1. Add up the raw infrastructure cost to run one camera for one month (compute + bandwidth + database/storage/monitoring + the fixed part of payment processing).
2. Add operating overhead (support, admin tooling, misc costs beyond raw cloud infra) as an explicit percentage on top — kept separate from profit margin, since PROJECT.md lists them as two different inputs.
3. Divide by `(1 − target gross margin)` to get a price that leaves the intended margin after cost.
4. Divide again by `(1 − payment processor's percentage cut)` so Vero actually nets the intended margin after PayPal takes its percentage of the charged price (the percentage fee scales with the final price, not the cost, so it has to be applied last).
5. Read off the result as a flat $/camera/month price.

## Assumptions

Each line states what it's based on and how confident it is. Two are genuine placeholders (no real usage data exists yet, because there are no real customers yet) and are marked as such.

| Assumption | Value | Basis |
|---|---|---|
| Compute per camera | 1 vCPU, continuously | **Measured**, not assumed — `docs/ROADMAP.md`: "~0.09s/frame on this dev machine's 4-core CPU... each active tracking session uses roughly one full CPU core at the ~5fps target rate" (Phase 5/11). CPU-only because no GPU code path exists or has been tested (Phase 13's `cloud-engine` and `backend` both pin `onnxruntime`, not `onnxruntime-gpu`; no `torch`+CUDA pin). |
| Hours tracked/day | 24 | The product has no scheduling feature — tracking runs until explicitly stopped. Matches actual behavior, not a business guess. |
| Reference compute instance | AWS `c7i.xlarge`, 4 vCPU, $0.1785/hr on-demand | Researched September 2026 (aggregated from Vantage/economize.cloud against AWS's own on-demand pricing page). On-demand, not Spot/Reserved — used as the conservative baseline since nothing is deployed yet to commit to a reservation. Regional price varies (~$0.178–0.214/hr seen); low end used. |
| Egress bandwidth rate | ~$0.085/GB | AWS/CloudFront first-10TB tier, researched September 2026. Ingress (camera stream → cloud) is free on AWS-style providers, so it is not a cost line — this is the opposite of the intuition that "streaming video to the cloud" is the expensive part; the expensive part is the CPU that watches it. |
| **Live View usage pattern** (drives egress volume) | 2 hrs/day/camera of a customer viewing Live View, polled every 3s, ~0.3 MB/annotated-frame | **Placeholder — flagged.** The 0.3 MB figure is real (Phase 13's live check measured a 319 KB annotated JPEG); the usage pattern (how often someone actually watches Live View) is an assumption with no real telemetry behind it. Revisit once there's real usage data. |
| Managed PostgreSQL | `db.t4g.medium`, ~$47.45/month + $0.115/GB-month storage | AWS RDS, researched September 2026. Shared across the whole Vero Cloud fleet, not per camera — structured events/heat snapshots are small (`docs/ROADMAP.md`, Phase 9: "a line crossing is one narrow row... heat is about 1 KB per camera per hour"), so 20 GB is generous headroom. |
| **Fleet size for amortizing shared DB/monitoring cost** | 100 concurrently-tracked cameras | **Placeholder — flagged.** An "early-stage scale" guess, not derived from anything measured. The DB/monitoring line is a small fraction of the total either way (compute dominates), so this assumption matters far less than the compute one, but it is still a guess. |
| Monitoring | +10% of DB compute+storage spend | No real monitoring stack has been chosen. A round placeholder, not researched. |
| Payment processing | PayPal, ~3.49% + $0.49/transaction | US standard tier, researched September 2026 (paypal.com/us/business/paypal-business-fees). One subscription charge per organization per month. |
| Cameras per paying customer | 5 | Your input — target customers (retail/warehouse/parking/office/construction) typically run multiple cameras; used only to spread the *per-organization* payment fixed fee across cameras. |
| Operating overhead | +25% on raw infra cost | Your input — a round, commonly-used SaaS rule of thumb for a small team's support/tooling/admin, kept as its own line per PROJECT.md rather than folded into margin. |
| Target gross margin | 70% | Your input. |

## The calculation

| Line | Basis | $/camera/month |
|---|---|---|
| Compute | 1 vCPU × 730 hrs/mo × ($0.1785/hr ÷ 4 vCPU = $0.04463/vCPU-hr) | $32.58 |
| Bandwidth (egress) | (2400 polls/day × 0.3 MB + ~1 GB/mo API traffic) ≈ 22.6 GB/mo × $0.085/GB | $1.92 |
| Database + storage + monitoring | ($47.45 DB + $2.30 storage) × 1.10 monitoring ÷ 100-camera fleet | $0.55 |
| Payment fee (fixed part) | $0.49/org/mo ÷ 5 cameras/org | $0.10 |
| **Raw infrastructure subtotal** | | **$35.15** |
| + 25% operating overhead | × 1.25 | $43.94 |
| ÷ (1 − 70% margin) | ÷ 0.30 | $146.46 |
| ÷ (1 − 3.49% PayPal cut) | ÷ 0.9651 | **$151.75** |

**Result: approximately $150–155/camera/month** for the Vero Cloud plan, at 70% gross margin, current CPU-only architecture, continuous 24/7 tracking. Not rounded to a marketing-ready number ($149, $155, etc.) here — that rounding choice is yours.

## Headline finding

**Compute is the overwhelming cost driver — roughly 93% of the raw infrastructure subtotal ($32.58 of $35.15).** This is the opposite of the common assumption that a video-adjacent cloud product is mostly a bandwidth/storage cost: raw video is never uploaded to persistent storage (per `docs/PROJECT.md`'s own rule) and ingress is free, so bandwidth is a minor line. The real cost is a CPU core running YOLO+ByteTrack inference continuously, for as long as tracking is active, per camera.

At this compute basis, the resulting price (~$150/camera/month) is materially higher than many existing camera-analytics SaaS products. This is a real result of the model, not a softened or rounded one, and is worth confirming is acceptable before it becomes a real price. Concrete levers that would lower it, none decided or implemented here since none was asked for:

- Lower the effective sampling rate or resolution per camera (reduces CPU-seconds consumed, at some cost to detection responsiveness).
- Share inference more efficiently across cameras (e.g., batching frames from multiple cameras through one model instance) rather than one dedicated core per camera.
- Use Spot or Reserved compute pricing instead of on-demand once there's a real deployment to commit against (on-demand was used here as the conservative baseline).
- Revisit GPU inference once a real, tested GPU deployment exists — GPU compute costs more per hour but can process many more camera-streams per instance, which could lower the effective per-camera cost; nothing here is tested against a GPU today, so this wasn't modeled.
- Accept a lower gross margin.

## What this document does not do

- **Does not change any code.** `Subscription.max_cameras` stays unset (`None`, unlimited) on every real organization — this document exists so Phase 15 (PayPal integration) has a real number to actually charge and enforce, not to wire one in ahead of billing existing.
- **Does not price Own Hardware.** That plan's price is a market-positioning decision, out of scope for this phase.
- **Does not decide pricing tiers or bundles.** This is a single flat per-camera price, per your structural decision — not "Starter/Growth/Business" packaging.
- **Does not use Spot/Reserved compute pricing, or model GPU inference.** On-demand, CPU-only — the conservative, verifiable baseline matching what's actually built and measured today.
- **Is not final.** Two assumptions (Live View usage pattern, fleet-size amortization) are explicitly flagged placeholders with no real usage data behind them; cloud provider prices researched September 2026 will drift; and whether ~$150/camera/month is commercially viable is a decision for you to make from this document, not one this phase makes for you.
