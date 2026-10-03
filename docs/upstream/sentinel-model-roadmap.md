# Model Roadmap — AI/ML Track
**Project:** Cybersecurity Sentinel — AI-Based Network Traffic Analysis and Automated Response System

This is the AI/ML track: detection models built and evaluated independently of the pipeline, against a fixed interface contract. None of it requires the live system to run or test.

---

## THE MODEL INTERFACE CONTRACT (read this first)

**GOAL**
The fixed request/response contract this track builds against, so the model can be dropped into the pipeline later without either side needing to change.

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
- `tier: "fast"` requests must respond within the inline latency budget the system sets (e.g. under 50ms) — this track owns hitting that, even if it means a lighter model runs on that tier.
- `tier: "deep"` requests have no hard latency ceiling.
- Every response must carry `model_version` — this is what makes multiple model variants comparable later.

**DELIVERABLE**
Adopt `CONTRACT.md` as-is from the system track before Step 1 starts. If a feature needs to change, flag it — don't diverge silently.

---

## STEP 1 — Contract Adoption & Local Test Harness

**GOAL** Stand up a service speaking the exact contract before any real model exists.

**TASKS**
- Start from a stub (fake, deterministic verdicts) as a placeholder — same shape the system track uses.
- Write a conformance test suite: valid request → schema-valid response, malformed request → clean error, latency check on the `fast` tier.

**DELIVERABLES**
- A service passing the same conformance tests the system track wrote its own stub against — this is the proof the two sides agree.

---

## STEP 2 — Dataset Preparation & Feature Engineering

**GOAL** Get labeled training data into the same feature shape the contract defines.

**TASKS**
- Pull 1-2 days of CICIDS2017/CSE-CIC-IDS2018.
- Build a feature extraction pipeline producing exactly the fields in the contract — must match the system track's live feature extraction field-for-field.

**RULES**
- Don't invent extra features the system doesn't compute yet — update the contract and flag it if you need one.

**DELIVERABLES**
- A labeled feature dataset, schema-validated against the contract.

---

## STEP 3 — Baseline Classical Model

**GOAL** A working, evaluable classifier before anything novel or GPU-based.

**TASKS**
- Random Forest / XGBoost on the Step 2 feature set.
- Wrap it behind the Step 1 service, replacing the placeholder logic.

**DELIVERABLES**
- Precision/recall/F1 on a held-out split — this is the baseline every later variant gets compared against.

---

## STEP 4 — Novel Detection: ZT-IP + JA3/JA4

**GOAL** Implement the Zero-Trust IP heuristic and TLS-fingerprint detection as a distinct, evaluable variant.

**TASKS**
- ZT-IP: flag connections to an IP not preceded by a DNS lookup for that IP within a configurable window.
- JA3/JA4: use an existing fingerprinting library, build a classification layer on top (known-malicious sets, anomalous fingerprint clustering).

**DELIVERABLES**
- Evaluation comparing this variant to the Step 3 baseline, specifically on malware/exfiltration-labeled traffic.

---

## STEP 5 — GPU-Accelerated Structural DPI

**GOAL** A second novel variant using entropy/compression/byte-frequency/n-gram features on GPU.

**TASKS**
- CPU baseline first (same features, plain Python/NumPy) for a real before/after.
- Port to GPU (CUDA or RAPIDS/cuDF) once the CPU version is correct.

**DELIVERABLES**
- Throughput comparison (flows/sec) CPU vs GPU, plus accuracy — both numbers matter for this one.

---

## STEP 6 — Packaging & Versioning

**GOAL** Make model swaps actually push-button.

**TASKS**
- Docker container per model variant, each exposing the same contract endpoint.
- `model_version` set per build; variants runnable side by side on different ports for comparison.

**DELIVERABLES**
- Three tagged, containerized services (baseline, ZT-IP+JA3/JA4, GPU-DPI), each independently swappable into the system.
