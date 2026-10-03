# System Roadmap — Core Pipeline
**Project:** Cybersecurity Sentinel — AI-Based Network Traffic Analysis and Automated Response System

This is the core pipeline track: capture, rule-based detection, alerting, dashboard, feedback loop. None of it requires a real AI model to build or test — every step below runs against a stub model service that speaks the same interface the real model will use later.

---

## THE MODEL INTERFACE CONTRACT (read this first)

**GOAL**
A fixed request/response contract the pipeline calls into, so the AI model can be swapped in later without touching this code.

**TRANSPORT**
- Primary: a local REST endpoint (`POST /infer`) — fastest to stand up and test on one machine.
- Optional later upgrade: a Kafka topic pair (`features-in` / `verdicts-out`) — matches the original architecture's Kafka pipeline, and is a straight swap once REST works since the payload schema doesn't change.

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

**RULES**
- `tier: "fast"` requests must respond within the inline latency budget set in Phase 0 (e.g. under 50ms).
- `tier: "deep"` requests have no hard latency ceiling — this is the offline path.
- Every response carries `model_version`, logged by the system, so you always know which model produced which verdict later.
- If the model endpoint is unreachable or slow, the system must fall back to Suricata/heuristic-only verdicts — define this fallback now, not when it breaks during a demo.

**DELIVERABLE**
A one-page `CONTRACT.md` committed to the repo before Step 1 starts.

---

## STEP 1 — Environment, Scope & Contract Stub

**GOAL** Get the dev environment running and a fake model endpoint in place so the pipeline has something to call.

**TASKS**
- Native Linux, libpcap, Suricata, Kafka via Docker (standard Phase 0 setup).
- Build a **stub model service**: a small Flask/FastAPI app implementing the contract exactly, returning a deterministic fake verdict (hash `flow_id` → benign/suspicious/malicious) instead of real inference.

**RULES**
- The stub must be schema-correct, not just close enough — the model track gets tested against it too.
- Kill the stub mid-run at least once and confirm the system degrades instead of crashing.

**DELIVERABLES**
- Stub responding to `POST /infer` in under 5ms.
- A README note on how to point the pipeline at a different model endpoint — this is the actual "plug" in plug & play.

---

## STEP 2 — Traffic Capture & Preprocessing

**GOAL** Capture traffic and turn it into the feature payload the contract expects.

**TASKS**
- libpcap/AF_PACKET capture → L2-L4 parsing → flow key generation.
- Compute the exact `features` fields from the contract (entropy, byte/packet counts, JA3 hash extraction, DNS-before-IP flag).

**RULES**
- Feature computation lives entirely on the system side — the model never sees raw packets, only the contract payload. This is what makes the split real.

**DELIVERABLES**
- A function turning a captured flow into a contract-valid `features` object, unit tested against hand-built sample flows.

---

## STEP 3 — Rule-Based Detection & Response Logic

**GOAL** Get Suricata, the DoS/DDoS heuristic, and blocking logic working end to end — none of it depends on the AI model.

**TASKS**
- Feed mirrored traffic to Suricata, consume EVE JSON.
- Rate/packet-count threshold detector for DoS/DDoS.
- Response logic combining Suricata + DoS verdicts + the model's verdict into a block/allow decision via nftables.

**RULES**
- The model's verdict is one input among several, never the sole trigger — keeps the system functional with the model degraded or absent.

**DELIVERABLES**
- Working inline path: capture → detect → call model → respond, with per-stage verdicts logged.

---

## STEP 4 — Alert & Log Pipeline

**GOAL** Every verdict lands in Kafka and is queryable.

**TASKS**
- Single-node Kafka alert topic; producer in response logic, consumer writing to Elasticsearch.
- Log `model_version` on every event, even the stub's fake version string.

**DELIVERABLES**
- Test-run alerts visible in Kibana, filterable by verdict source and `model_version`.

---

## STEP 5 — Offline Path Skeleton

**GOAL** Pcap recorder and threat correlator shell, no real ML output required.

**TASKS**
- tcpdump-based rotating pcap buffer.
- Threat correlator: time-window correlation on the Step 4 alert stream, calling the model's `deep` tier via the stub.

**DELIVERABLES**
- Correlated incident records from a replayed attack pcap, using stub verdicts.

---

## STEP 6 — Dashboard

**GOAL** Real-time and historical views wired to whatever's flowing through Kafka — stub or real model, the dashboard doesn't care.

**TASKS**
- Kibana/Grafana: live alert feed, historical search, a panel breaking verdicts down by `model_version`.

**DELIVERABLES**
- Dashboard fully demoable using only the stub.

---

## STEP 7 — Feedback Loop (stub-driven)

**GOAL** Build the loop pushing offline findings back into inline rules, triggered by the stub for now.

**TASKS**
- Automated Feedback Controller consuming `malicious` deep-tier verdicts, generating an nftables/XDP rule update.

**RULES**
- Require a confidence threshold before auto-pushing a rule — a bad stub verdict shouldn't block legitimate traffic during testing.

**DELIVERABLES**
- A stub-triggered malicious verdict visibly changing inline block rules within a test run.
