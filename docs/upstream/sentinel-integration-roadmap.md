# Integration Roadmap
**Project:** Cybersecurity Sentinel — AI-Based Network Traffic Analysis and Automated Response System

Run this after the System and Model tracks each have working pieces. Every step here assumes the contract below was honored by both sides independently — this is where that assumption gets tested for real.

---

## THE MODEL INTERFACE CONTRACT (what's being integrated against)

**REQUEST SCHEMA**
```json
{
  "flow_id": "string",
  "tier": "fast" | "deep",
  "features": {
    "duration_ms": number,
    "byte_count": number,
    "packet_count": number,
    "protocol": "string",
    "entropy": number,
    "ja3_hash": "string | null",
    "dns_before_ip": boolean
  },
  "timestamp": "ISO8601"
}
```

**RESPONSE SCHEMA**
```json
{
  "flow_id": "string",
  "verdict": "benign" | "suspicious" | "malicious",
  "confidence": number,
  "model_version": "string",
  "latency_ms": number
}
```

**KEY RULES**
- Fast tier has a hard latency budget (e.g. under 50ms); deep tier doesn't.
- Every response carries `model_version`.
- The system falls back to Suricata/heuristic-only verdicts if the model is unreachable or slow.

---

## STEP 1 — Contract Conformance Cross-Check

**GOAL** Prove the system's expectations and the model's actual behavior match, formally, before wiring them together live.

**TASKS**
- Run the system track's contract tests against each real model container.
- Run the model track's conformance suite against real system-generated features, not synthetic payloads.

**DELIVERABLES**
- A passing cross-check report — every real model variant accepts real system-generated features and returns schema-valid responses.

---

## STEP 2 — Swap Stub for Real Model (staging)

**GOAL** Replace the stub endpoint with a real model container, no pipeline code changes.

**TASKS**
- Point the system's model-endpoint config at the baseline model container.
- Re-run every system-side pipeline test unchanged — they should all still pass, just with real verdicts now.

**RULES**
- If a pipeline test breaks here, the bug is in the contract or the feature extraction — not something to patch around case by case.

**DELIVERABLES**
- Full pipeline running end to end with the real baseline model, zero changes to system-side code.

---

## STEP 3 — Latency & Load Validation

**GOAL** Confirm the fast-tier model actually holds the inline latency budget under realistic load, not just in isolation.

**TASKS**
- Replay sustained traffic (Scapy/hping3) through the full inline path with the real model attached.
- Measure end-to-end latency, not just the model's own response time — capture, feature extraction, and network overhead all count.

**DELIVERABLES**
- A latency report against the contract's budget; if it's blown, decide whether the fast tier needs a lighter model or the budget needs revising.

---

## STEP 4 — Feedback Loop Activation

**GOAL** Wire the real deep-tier model's verdicts into the automated feedback controller, replacing the stub trigger.

**TASKS**
- Point the feedback controller at the real offline model instead of the stub.
- Re-verify the confidence-threshold/rate-limit guardrails still hold with real, noisier model output.

**DELIVERABLES**
- A real malicious verdict from the deep-tier model visibly updating inline block rules, end to end.

---

## STEP 5 — Model Variant Comparison in Production Shape

**GOAL** Run all three model variants through the same live pipeline to get comparable, apples-to-apples numbers for the report.

**TASKS**
- Swap each container in turn (Step 2's process), same traffic replay, same dashboard.
- Use the dashboard's `model_version` breakdown to compare detection rates and latency across variants without extra tooling.

**DELIVERABLES**
- A side-by-side results table across all three variants, generated from real pipeline runs rather than isolated model evaluation.

---

## STEP 6 — Documentation

**GOAL** Anyone — including future-you — can swap in a new model without reading the code.

**TASKS**
- Write up the final `CONTRACT.md`, the config flag for pointing at a different model endpoint, and the conformance test suite as the "how to plug in a new model" doc.

**DELIVERABLES**
- A short `INTEGRATION.md` in the repo: contract spec, how to swap models, how to run the conformance check.
