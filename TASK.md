# TASK.md — W-MSTSE Detection Model

**Project:** Cybersecurity Sentinel — AI-Based Network Traffic Analysis and Automated Response System
**Track:** AI/ML (model track) · **Model name:** `wmstse` · **Repo root / working dir:** `<project_dir>/wmstse/`
**Companion file:** `ROADMAP.md` (ordered phases, exit gates, git checkpoints)

This file defines **what** to build, the **rules**, and the **acceptance criteria**. `ROADMAP.md` defines the **order** and the **gates**. Read both fully before writing any code.

---

## 0. Authority and conflict resolution

When two sources disagree, the higher one wins. Record every deviation in `docs/DECISIONS.md` (one entry each: context, options, decision, evidence).

1. `contract/CONTRACT.md` — vendored from the system track; never edit it
2. This file (`TASK.md`)
3. `ROADMAP.md`
4. Upstream roadmaps in `docs/upstream/` (`sentinel-model-roadmap.md` is primary; the system and integration roadmaps are context)
5. Your own judgement

---

## 1. Summary

**W-MSTSE** (Wavelet-Decomposed Multi-Scale Shannon Entropy Tensors) detects volumetric and multi-vector DDoS activity by turning traffic into a 2-D "entropy spectrogram" and classifying it with a lightweight vision model.

- **Prior art:** Shannon entropy over a single 1-D sliding window (of packet arrivals or IPs). An attack is flagged when entropy drops rapidly.
- **Novelty:** decompose the traffic signals into several frequency sub-bands first, compute entropy per sub-band, stack the results into an image-like tensor, and let a vision model learn cross-band structure (e.g., a simultaneous entropy drop in high-frequency bands and a rise in low-frequency bands) that single-scale entropy cannot express.
- **Derivation:** adapted from audio (Mel-spectrograms) and EEG analysis, where signal components are separated by frequency before classification.

Pipeline:

```
flow records (event-time stream)
  → fixed-width time bins               (order-independent sums per bin)
  → per-channel signals over T bins     (len, pkt-rate, flow-rate)
  → wavelet decomposition               (B sub-bands per channel)
  → rolling Shannon entropy per band    (fixed bin edges, fit on train only)
  → entropy tensor  X ∈ R^{C × B × T_out}
  → MobileNetV2 / ViT-Tiny              → calibrated P(attack)
  → verdict mapping                     → benign | suspicious | malicious
```

It ships as a Docker container exposing `POST /infer` per the Sentinel Model Interface Contract, so it can replace the stub or any other variant with **zero system-side code changes**.

---

## 2. Where this fits in Sentinel

- This is a **model-track variant** (analogous to Steps 4–5 of `sentinel-model-roadmap.md`), developed and evaluated independently of the live pipeline, against the fixed contract.
- The model **never sees raw packets**. The system computes features; the model sees only the contract payload.
- The system treats the model verdict as **one input among several**, never the sole trigger, and falls back to Suricata/heuristics if the model is unreachable or slow.
- Roadmap step mapping: Step 1 (contract adoption + harness) → P0 · Step 2 (dataset + features) → P1–P4 · Step 3 (baseline) → P5 · Steps 4/5 (novel variant) → P3–P7 · Step 6 (packaging/versioning) → P8.

### 2.1 Contract fields: what W-MSTSE consumes

| Contract field | Used? | How |
|---|---|---|
| `flow_id` | yes | echoed in response; dedupe key |
| `tier` | yes | `fast` → cached window verdict; `deep` → synchronous recompute |
| `timestamp` | yes | event time for binning (semantics per CONTRACT.md — see D7) |
| `features.byte_count` | yes | per-bin byte sum → mean-packet-length signal |
| `features.packet_count` | yes | per-bin packet sum → packet-rate and mean-packet-length signals |
| `features.duration_ms` | light | sanity check; optional emission-time correction (D7) |
| `features.protocol` | validated | not part of the v1 tensor (may be used in an ablation) |
| `features.entropy` | **ignored** | schema-validated only. This is the system's per-flow payload entropy — **not** W-MSTSE's entropy (D9) |
| `features.ja3_hash` | ignored | accepts `null` and strings |
| `features.dns_before_ip` | ignored | boolean, validated |

---

## 3. Critical design decisions (read before coding)

**D1 — Flow-record granularity, not PCAP.** The dataset is the precleaned CIC-DDoS2019 *flow-level* CSV, and the contract forbids raw packets reaching the model. "Packet lengths" and "inter-arrival times" are therefore represented at flow-record granularity per time bin: **mean packet length** (bytes ÷ packets), **packet rate** (packets/bin), and **flow arrival rate** (flows/bin, the flow-level analogue of inter-arrival time, since mean flow IAT ≈ Δ ÷ flows-per-bin). Packet-level IAT is not observable through the contract; adding it would be a contract change request (CR-3), not a v1 feature. PCAP parsing is a non-goal.

**D2 — Verdicts are window-level.** W-MSTSE classifies the *traffic window* containing the flow, not the flow itself. Every flow in the same window receives the same verdict; a benign flow during a DDoS gets `malicious`. This is an "attack in progress" signal. `MODEL_CARD.md` and `HANDOFF.md` must say so plainly: consumers must not use it as a standalone per-flow/per-source block trigger.

**D3 — Stateful serving without changing the contract.** The contract request carries one flow, but the model needs a window. The service keeps an in-memory, **event-time** ring buffer of per-bin sums built *only* from contract fields. No new request fields. Consequences: exactly one worker process; the inline stream must send **every** flow (no sampling); separate streams (live vs. offline pcap replay) need separate instances unless CR-4 (`stream_id`) is approved.

**D4 — DWT default, SWT ablation.** The brief specifies a Discrete Wavelet Transform (`pywt.wavedec`). Decimated DWT yields bands of different lengths and is not shift-invariant (the tensor can change if the window slides by one bin). Default: `mode="periodization"` (band *j* has exactly `T/2^j` coefficients), rolling-entropy series linearly resampled to a common `T_out`. The undecimated alternative (`pywt.swt`: equal-length bands, shift-invariant, `T` divisible by `2^level`) is a **required ablation**. Switch the default only on evidence (rule in ROADMAP P7).

**D5 — Class-imbalance direction is unverified.** The brief says normal traffic heavily outweighs attack traffic. The published CIC-DDoS2019 CSVs are typically *attack-dominated* at the flow level. P1 must measure imbalance at flow **and** window level. Metric choices (macro-F1, per-class F1, PR-AUC for both classes) must not assume a direction.

**D6 — "97–99% F1" is a target, evaluated leakage-safe.** Random row/window splits on this dataset are known to inflate scores because adjacent windows and same-session attack flows are near-duplicates. Headline numbers use blocked-temporal splits with gaps (P-A); a cross-session split (P-B) is reported alongside. **Never change the protocol, tune on test, or re-label to hit the target.** A truthful 90% is a valid result; a leaked 99% is a failure.

**D7 — Timestamp semantics.** CICFlowMeter's `Timestamp` is flow *start*; the system may send flow *end*/emit time. The stream order used in training must match what the service will see. Take the semantics from `CONTRACT.md`; if silent, default to `start`, expose a `timestamp_semantics: start|end` config (`end` = start + duration), and open CR-1 for clarification.

**D8 — Fast tier via a per-bin cache.** A CNN/ViT forward pass per request would threaten the latency budget. The window classification is computed once per *closed* bin on a background worker; `fast` requests read the cached result (O(1)). `deep` requests recompute synchronously on the freshest closed bins (optionally with test-time offset averaging). Same weights and same `model_version` for both tiers. If the budget still cannot be met, apply the remedy ladder in ROADMAP P8.

**D9 — Two different "entropies".** Contract `features.entropy` = system-computed payload entropy. W-MSTSE entropy = Shannon entropy of wavelet-coefficient distributions computed inside the model. Never reuse, mix, or rename one as the other.

---

## 4. Goals

- **G1** A contract-exact service (`POST /infer`, both tiers, `model_version` on every response) that passes the vendored system-track conformance suite and our additions.
- **G2** A reproducible dataset → stream → tensor → model pipeline built on the precleaned CIC-DDoS2019 CSV, with the dataset *validated* (not re-cleaned).
- **G3** A leakage-safe evaluation comparing W-MSTSE against A0 (per-flow classical baseline), A1 (single-scale entropy, i.e., the prior art) and A2 (window statistics, no entropy/no wavelet).
- **G4** Evidence for or against the novelty claim (multi-scale vs. single-scale) with paired confidence intervals. A negative result is acceptable if reported honestly.
- **G5** Target detection quality of **97–99% F1** on the P-A split (reported as macro-F1 and per-class F1), with P-B reported as generalization evidence.
- **G6** Fast-tier latency within the contract budget (default p99 ≤ 50 ms, design target ≤ 10 ms server-side) on CPU only.
- **G7** A tagged, versioned, containerized artifact that can be swapped into the system, plus the documentation for doing so (`MODEL_CARD.md`, `HANDOFF.md`, `DATA_SPEC.md`, `DECISIONS.md`, `EVALUATION.md`).

## 5. Non-goals

- No system-track code: no capture, Suricata, nftables/XDP, Kafka, Elasticsearch/Kibana, dashboards, feedback controller.
- No raw-packet or PCAP handling; no feature extraction from packets (the system owns that).
- No contract changes. Needs go into `docs/CONTRACT_CHANGE_REQUESTS.md` (§17) and are **not** implemented unilaterally.
- No Kafka transport (REST only in v1).
- No ZT-IP, JA3/JA4 or GPU-DPI work (those are other variants).
- No data-cleaning pass. The dataset is precleaned; P1 validates it. The raw files are read-only. Only the minimum filters required for correctness are allowed, each recorded with counts and rationale.
- No per-flow malicious-flow classification, source attribution, or attack-family classification in v1 (stretch only).
- No online learning, no GPU requirement at inference, no multi-worker/horizontal scaling in v1.
- No chasing the accuracy target through leakage, test-set tuning, or silent label changes.

---

## 6. Objectives and success measures

| ID | Objective | Measure | Target |
|---|---|---|---|
| O1 | Contract conformance | vendored + added conformance tests, run on the built container | 100% pass |
| O2 | Dataset validity established | `reports/P1_dataset_audit.md` verdict | PASS or PASS-WITH-CAVEATS; no unresolved BLOCK |
| O3 | Detection quality, P-A split, independent windows | macro-F1 and attack-class F1 (95% block-bootstrap CI) | **≥ 0.97 target** (band 0.97–0.99); minimum acceptable: beats A1 and A2 with CI not overlapping, or an honest explanation |
| O4 | Generalization, P-B split | macro-F1, per-attack-type recall | reported; no target |
| O5 | Novelty evidence | single-scale (B=1) vs. multi-scale ablation, paired CI | reported either way |
| O6 | Fast-tier latency | server-side p50/p95/p99 under replay load | p99 ≤ 50 ms (hard); ≤ 10 ms (design) |
| O7 | Train/serve parity | max abs diff offline-vs-service: tensor ≤ 1e-5, P(attack) ≤ 1e-4 | pass |
| O8 | Reproducibility | clean clone + `make reproduce-small` on synthetic fixture | identical tensors; metrics within 1e-3 |
| O9 | Packaging | container built from a clean tag, run fresh, conformance green | pass |
| O10 | Documentation | `MODEL_CARD`, `HANDOFF`, `DATA_SPEC`, `DECISIONS`, `EVALUATION`, `README`, `CHANGELOG` | present, accurate, every number traceable |

---

## 7. Data requirements

**Dataset:** CIC-DDoS2019 *precleaned* CSV files (path supplied by the user as `DATASET_DIR`). Use the capture days present; if two days are identifiable by timestamp, keep them separate (needed for P-B).

### 7.1 Hard rules
- **Raw files are immutable.** Convert once to Parquet under `data/interim/` (gitignored). Record SHA-256, size, row count in `data/MANIFEST.json` (committed).
- **Never subsample rows randomly.** This is a time-series method; random row sampling destroys temporal structure. If you must reduce volume, take **contiguous time spans** (including benign and attack periods) and record which.
- **No cleaning pass.** Validate; report; apply only the minimum correctness filters (e.g., unparsable timestamp, negative duration) with counts in `DECISIONS.md`.
- Strip/normalize column names (leading spaces are common) via an explicit rename map in `DATA_SPEC.md`. Do not assume column names — verify them against the actual files.
- Stream large files with polars/pyarrow (lazy/chunked). Do not load multi-GB CSVs into a single pandas DataFrame.

### 7.2 Dataset validity audit (P1) — required checks
| # | Check |
|---|---|
| A1 | File inventory: name, size, rows, SHA-256 |
| A2 | Schema: columns, dtypes; presence of timestamp, label, duration, forward/backward packet counts and byte lengths, protocol |
| A3 | Timestamp: parse rate, timezone/format, per-file range, monotonicity, gaps, duplicates, usable ordering |
| A4 | Labels: distinct values, counts per file/day, benign:attack ratio at flow level, per-attack-type time ranges |
| A5 | Value validity: NaN/Inf, negatives, zero-packet flows, outliers; flows extending past capture end |
| A6 | Exact duplicate rows (count only; no removal) |
| A7 | Cross-file overlap/consistency (same flows or time ranges in multiple files) |
| A8 | Label-vs-time sanity: attack labels sit in contiguous periods consistent with attack-type timing |
| A9 | Contract-mapping coverage: `byte_count`, `packet_count`, `duration_ms`, `protocol`, `timestamp` derivable for ≥ 99.9% rows |
| A10 | Window feasibility: benign/attack **window** counts per split at default (Δ, T) |
| A11 | Imbalance direction at window level (D5) |

Verdict: `PASS`, `PASS-WITH-CAVEATS` (list them), or `BLOCK`.

### 7.3 Blocking conditions (stop and report; do not proceed on a proxy)
- **B1** No usable timestamp (missing, unparsable, or non-chronological with no recoverable order). A row-index "time axis" is **not acceptable** without a written user decision.
- **B2** Labels unusable (single class, or labels not mappable to benign/attack).
- **B3** Fewer than 30 windows of any class in the test split at any (Δ, T) in the allowed grid — F1 cannot be estimated reliably.

On a block: write `reports/BLOCKER-<id>.md` (evidence, options, recommended path), commit, and stop work that depends on it.

---

## 8. Method specification

### 8.1 Canonical flow stream
Each CSV row → a `FlowRecord`: `event_ts`, `byte_count` (fwd+bwd bytes), `packet_count` (fwd+bwd packets), `duration_ms` (CICFlowMeter reports microseconds — convert and document), `protocol` (map numeric to the CONTRACT vocabulary), `label_binary`, `label_type`, `row_id`. Sort by `event_ts` with stable tie-break on `row_id`. Every record must be convertible into a schema-valid contract request (validated against `contract/schemas/`).

### 8.2 Binning and signals (order-independent, mergeable)
Per bin of width Δ keep **sufficient statistics only**: `n_flows`, `sum_bytes`, `sum_packets`. Channels (C = 3):

| Channel | Definition | Role |
|---|---|---|
| `len` | `sum_bytes / sum_packets` (explicit convention for empty bins) | packet-length analogue |
| `rate_pkts` | `log1p(sum_packets)` | volume |
| `rate_flows` | `log1p(n_flows)` | flow-IAT analogue (D1) |

Empty bins are valid zeros — not missing. Because the statistics are sums, late/out-of-order records can be merged into their bin and offline/online parity is achievable by construction. Single-channel variants (`len` only, `rate_flows` only) are ablations.

### 8.3 Windowing and labels
- Window = `T` consecutive bins; train stride `S` bins; independent-eval windows use stride `T`; streaming eval uses stride 1.
- **Window label:** attack iff the attack-flow fraction in the *trailing* `label_tail_bins` bins ≥ `τ` **and** attack flows ≥ `min_attack_flows`. Also store `attack_fraction` and majority `attack_type` as metadata. Windows with `0 < attack_fraction < 1` are "boundary windows": reported separately, never dropped silently.

### 8.4 Wavelet decomposition
- `pywt.wavedec(signal, wavelet, level, mode)` → `level + 1` arrays `[cA_L, cD_L, …, cD_1]`. **4–6 sub-bands ⇒ `level` 3–5.**
- Assert `level ≤ pywt.dwt_max_level(T, wavelet.dec_len)` and `T % 2**level == 0`; fail loudly otherwise (e.g., `db4` at `T=128` supports only level 3).
- Tests: perfect reconstruction (`waverec`), Parseval/energy preservation for orthogonal wavelets under `periodization`, synthetic signals (sine, impulse train, white noise, step) landing in the expected bands.
- `kind: dwt | swt` behind one interface.

### 8.5 Rolling Shannon entropy and tensor
- For each (channel, band): rolling window of `w_j = max(8, round(span / 2^j))` coefficients, stride 1.
- Per rolling window: histogram of coefficient **magnitudes** with `K` bins whose **edges are fit on training windows only** (per channel and band, quantile-based), `H = −Σ p·log2 p` with `0·log 0 = 0`, normalized by `log2 K` to `[0, 1]`.
- Linearly resample each band's entropy series to `T_out` columns; stack bands → `X ∈ R^{C × B × T_out}`.
- Fit-on-train artifacts (entropy edges, per-channel normalization stats) are saved with hashes; a test enforces they were computed from train indices only.
- Document the effective time span per band in `DATA_SPEC.md` (coarse bands integrate longer spans — that is the point of multi-scale).

### 8.6 Models
| ID | Model | Role |
|---|---|---|
| M-main-1 | MobileNetV2 (ImageNet-pretrained) | candidate |
| M-main-2 | ViT-Tiny (ImageNet-pretrained, e.g., timm) | candidate |
| M-floor | Tiny custom CNN, scratch | sanity floor |

- Input mapping from `C × B × T_out` to the backbone input size (default 64×64): evaluate bilinear resize vs. nearest-neighbour band-row repetition (preserves sharp band boundaries). Check the pretrained-weight loading path when changing `img_size`/`patch_size`; if weights cannot be downloaded (offline), train from scratch and log it.
- Loss: class-weighted cross-entropy (or focal). Optimizer: AdamW, cosine schedule, early stopping on **validation macro-F1**. 3 seeds per configuration; report mean ± std.
- Augmentation (allowed): small window-offset re-sampling, mild time masking, amplitude jitter. **Not allowed:** flips across the band axis or the time axis, mixup across classes.
- Export the selected model to **ONNX**; torch↔ONNX parity must hold (max abs logit diff ≤ 1e-3). The serving image must not require torch or a GPU.

### 8.7 Default configuration (all values live in `configs/default.yaml`; every run records the resolved config)
| Key | Default | Notes |
|---|---|---|
| `bin_width_s` (Δ) | 1.0 | grid: 0.5, 1, 2 |
| `window_bins` (T) | 256 | divisible by `2^level` |
| `train_stride_bins` | 8 | |
| `channels` | `len, rate_pkts, rate_flows` | |
| `wavelet` / `level` / `mode` | `db4` / 4 (→ 5 sub-bands) / `periodization` | ablate `haar`, `sym4`; levels 3, 4, 5 |
| `entropy_bins` (K) | 16 | quantile edges, train-fit |
| `entropy_span_bins` | 32 | per-band `w_j` rule in §8.5 |
| `T_out` | 64 | |
| `label_tail_bins` / `τ` / `min_attack_flows` | 16 / 0.5 / 5 | |
| `input_size` | 64 | ablate 96 |
| `lateness_bins` | 2 | serving |
| `timestamp_semantics` | `start` | D7 |
| `seeds` | 3 | |
| `thresholds` | selected on validation | §10.4 |

---

## 9. Evaluation protocol

### 9.1 Splits (leakage-safe; indices saved and hashed)
- **P-A — blocked temporal, in-session (headline for O3).** Cut the timeline into contiguous segments (maximal runs of the same label-type; benign gaps are their own segments). Within each segment: first 70% → train, next 15% → val, last 15% → test, with a gap ≥ `T` bins between adjacent blocks; any window overlapping a gap is dropped. Segments too short to split go wholly to train (noted).
- **P-B — cross-session (generalization, O4).** Train/val from the earlier capture day(s), test from the later day; val = last 15% blocks of the train day with gaps. Mark N/A if timestamps expose only one day.
- **Leakage tests (must pass in CI):** no flow in two splits; no window pair across splits overlaps in time; preprocessing is fit on train only; test windows are never used for threshold/edge/normalization choices.
- The **test split is touched only by `eval/final_report.py`** after the `config-freeze` tag. Any later change requires a new tag and a DECISIONS entry noting test re-use.

### 9.2 Metrics
- **Window-level (primary):** per-class precision/recall/F1 (attack and benign), **macro-F1**, MCC, PR-AUC (attack-positive and benign-positive), confusion matrix, 95% **block-bootstrap** CIs.
- **Flow-level inherited:** each flow takes its window's verdict; report per-class and macro metrics (expect dominance by the majority class — say so).
- **Streaming (stride 1):** detection delay (bins/seconds from attack onset to first `malicious`), false-positive windows per benign hour, **verdict flip rate** under a 1-bin shift of the window start (stability; relevant to D4).
- **Per-attack-type recall** table; boundary-window metrics reported separately.
- **Latency/throughput:** p50/p95/p99 per tier; tensor-build and inference time per window.

### 9.3 Baselines (all on identical splits and windows)
| ID | Baseline | Purpose |
|---|---|---|
| A0 | Per-flow RF/XGBoost on contract-available features (`duration_ms`, `byte_count`, `packet_count`, `protocol`), aggregated to windows by mean predicted probability | Model-roadmap Step 3 analogue |
| A1 | **Prior art:** single-scale rolling Shannon entropy over the same signals (no wavelet), threshold detector + XGBoost on entropy statistics | tests the novelty claim |
| A2 | Window statistics of the per-bin signals (mean, std, skew, quantiles; no entropy, no wavelet) → XGBoost | rules out "volume stats suffice" |
| A3 | Flattened W-MSTSE tensor → XGBoost/logistic | separability probe before deep training |

### 9.4 Ablations (one-factor-at-a-time around the default; ≥ 3 seeds; decided on **validation**, reported on test once after freeze)
1. Single-scale (B=1) vs. multi-scale (B=4–6) — the core claim
2. Channels: `len` only, `rate_flows` only, all three
3. Wavelet: `haar`, `db4`, `sym4`; level 3/4/5
4. DWT vs. SWT (decision rule in ROADMAP P7)
5. Entropy `K` and span
6. Backbone: MobileNetV2 vs. ViT-Tiny vs. custom CNN; pretrained vs. scratch
7. Window `T` and bin width Δ
8. Input mapping: resize vs. row repetition

### 9.5 Robustness (reported, not gated)
Timestamp jitter, bin-phase offsets, 5–20% random flow dropout (simulated sampling), out-of-order delivery within the lateness bound.

---

## 10. Serving specification

### 10.1 Endpoint
`POST /infer` exactly per `CONTRACT.md`. Optional ops endpoints (`GET /healthz`, `GET /version`) are *not* part of the contract; the system must not depend on them. Single uvicorn worker (`--workers 1`). Port configurable via `PORT`.

### 10.2 State
Event-time ring buffer of `(n_flows, sum_bytes, sum_packets)` per bin, sized `T + margin`; a bin is **closed** when the watermark passes `bin_end + lateness_bins·Δ`. On bin close, a background worker builds the tensor, runs ONNX inference, and publishes the result atomically to a cache.

### 10.3 Tier behaviour
- `fast`: validate → merge into buffer → return the cached window verdict (O(1)). Never run a forward pass on the request path.
- `deep`: validate → merge → synchronously rebuild the tensor from the freshest closed bins, run inference (optionally average over a few window offsets), return. No hard latency ceiling (soft target ≤ 500 ms).

### 10.4 Verdict mapping and `confidence`
- `p_attack` = temperature-scaled probability (temperature fit on validation).
- `p_attack < τ_low` → `benign`; `τ_low ≤ p_attack < τ_high` → `suspicious`; `p_attack ≥ τ_high` → `malicious`. Thresholds are chosen on validation (default rule: `τ_high` = lowest threshold with validation attack-precision ≥ 0.99; `τ_low` = highest threshold with validation attack-recall ≥ 0.99), stored in `thresholds.json` inside the model artifact.
- `confidence`: `malicious` → `p_attack`; `benign` → `1 − p_attack`; `suspicious` → `p_attack`. Always in `[0, 1]`. Mapping must be monotonic in `p_attack` (tested).
- `latency_ms` = server-side processing time for that request (the integration track measures end-to-end).
- `model_version` = `wmstse-<semver>+<git-sha7>`, injected at build time (§11).

### 10.5 Required edge-case behaviour
| Case | Behaviour |
|---|---|
| Cold start (< T closed bins) | `benign`, `confidence 0.0`; warm-up counter; documented in HANDOFF (open CR-2 for an explicit flag) |
| Malformed request | clean 4xx JSON error; **state untouched**. Use the status code the vendored conformance tests expect; if unspecified use 422 and note it in CR-5 |
| Duplicate `flow_id` (within dedupe horizon, LRU) | respond normally; do not double-count |
| Out-of-order within lateness | merged into its bin |
| Older than the buffer horizon | not counted; respond from cache; counter incremented |
| Repeated beyond-horizon (e.g., pcap replay restarted) | after `regression_reset_count` consecutive, reset state and log WARN (policy deterministic and tested) |
| Idle gap | empty bins are zeros |
| Burst with identical timestamps | counted; no division by zero |
| Concurrent requests | thread-safe; no torn reads of the cached verdict |
| Negative/non-finite numbers | rejected as malformed |
| Unknown extra fields | follow vendored conformance tests; default ignore |
| `ja3_hash: null` | accepted |

### 10.6 Latency budget
Contract: fast tier within the system's inline budget (default 50 ms). Design target ≤ 10 ms p99 server-side so the integration track's end-to-end measurement (capture, extraction, network) still fits. Measure under replay load at several request rates (default 100, 500, 1000 req/s), not just in isolation.

### 10.7 Offline/online parity
Offline tensor builder uses vectorized polars/NumPy; the service uses an incremental accumulator. They must agree (O7): property tests on random streams plus a replay of ≥ 1 hour of real test-split data through the HTTP service, comparing per-window tensors and `p_attack`.

### 10.8 Hand-off requirements (`docs/HANDOFF.md`)
State, for the system track: send every flow in near-time order; timestamp semantics; one instance per stream; warm-up behaviour; window-level meaning of verdicts (D2); recommended use as one input among several; thresholds and expected operating point; known limits; the train/serve-skew risk between CICFlowMeter flow semantics and the system's flow generator, and what Integration Steps 1 and 3 should re-check.

---

## 11. Packaging and versioning

- One Docker image: multi-stage, non-root, CPU-only, pinned dependencies, ONNX Runtime (no torch). Build args: `MODEL_VERSION`. Env: `PORT`, config overrides. Healthcheck optional.
- `model_version = wmstse-<semver>+<git-sha7>`. **Release builds fail on a dirty working tree.** The image tag is `wmstse:<semver>`; never use `latest`.
- Release artifact directory `artifacts/release/<model_version>/`: `model.onnx`, `thresholds.json`, `entropy_edges.npz`, `norm_stats.json`, `config.resolved.yaml`, `MANIFEST.json` (sha256, sizes, git SHA, dataset manifest hash, metrics summary). Track the `model.onnx` with Git LFS if available; otherwise exclude it and reference its checksum in the committed manifest (log the choice).
- Must run side-by-side with other variants on a different port.

---

## 12. Version control rules

Repository root is `<project_dir>/wmstse/` and it is its **own git repository**.
- If `.git` already exists there, **resume**: read `STATUS.md` and `git log`, skip phases whose tags exist. Do not re-init.
- If `<project_dir>` is itself a git repository, do not modify the parent repo; note the nesting in the final report so the user can choose submodule vs. subtree.

**Branches:** `main` is always green and only receives `--no-ff` merges of phase branches after the gate passes. Work on `phase/P<n>-<slug>` (and optional `feat/<slug>` off a phase branch). Never force-push or rewrite history on `main`.

**Commits:** Conventional Commits with the phase as scope — `feat(P3): add DWT decomposition with level guard`, `test(P2): leakage checks for blocked splits`, `docs(P1): dataset audit report`. Small, logical, each with its tests. Run `make check` before every merge.

**Tags (annotated, message = gate summary):** `phase-P0-contract-stub`, `phase-P1-audit`, `phase-P2-stream-windows`, `phase-P3-wavelet`, `phase-P4-tensors`, `phase-P5-baselines`, `protocol-freeze` (end of P5), `phase-P6-training`, `config-freeze` (before final test eval), `phase-P7-evaluation`, `phase-P8-release`, and the release `v0.1.0`.

**What is committed:** code, configs, tests, small reports/figures, manifests, docs, `CHANGELOG.md`, `STATUS.md`, lock file. **Never committed:** raw/interim data, tensors, checkpoints (except via LFS/manifest rules in §11), secrets, `.venv`.

**Evidence trail:** each gate writes `reports/gates/P<n>.md` (phase, git SHA, commands run, key numbers, checklist, deviations, open issues). Every metric in any report must come from a committed script + committed config + recorded git SHA, with the reproduce command beside it.

**Reproducibility:** fixed seeds; resolved config saved with every run; `pyproject.toml` + lock file; split index files hashed; dataset manifest hashed.

---

## 13. Repository layout

```
wmstse/
├── TASK.md  ROADMAP.md  README.md  STATUS.md  CHANGELOG.md
├── pyproject.toml  Makefile  .gitignore  .pre-commit-config.yaml
├── configs/            default.yaml, eval_protocol.yaml, ablations/
├── contract/           CONTRACT.md (vendored), schemas/, conformance/
├── docs/
│   ├── upstream/       the three sentinel-*.md files (read-only copies)
│   ├── DATA_SPEC.md  DECISIONS.md  MODEL_CARD.md  HANDOFF.md
│   └── CONTRACT_CHANGE_REQUESTS.md
├── src/wmstse/
│   ├── data/           audit, stream, windowing, splits
│   ├── signals/        bins (vectorized + incremental accumulator)
│   ├── wavelet/        decompose (dwt|swt)
│   ├── entropy/        rolling, tensor, fit_edges
│   ├── models/         baselines, vision, train, calibrate, export_onnx
│   ├── eval/           metrics, bootstrap, ablations, stability, final_report
│   └── serve/          app, state, infer, verdict
├── tests/              unit/, property/, leakage/, conformance/, serving/, fixtures/
├── tools/              make_synthetic_stream.py, replay_csv.py, loadtest.py, make_report.py
├── data/               (gitignored) + MANIFEST.json
├── artifacts/          (gitignored) + MANIFEST.json, release/
├── reports/            audit, baselines, evaluation, latency, gates/, figures/
└── docker/             Dockerfile, .dockerignore
```

Make targets: `check`, `audit`, `streams`, `tensors`, `baselines`, `train`, `eval`, `serve`, `loadtest`, `docker`, `reproduce-small`.

Tests must run **without the real dataset** using `tools/make_synthetic_stream.py` (known benign background plus injected volumetric bursts across several bands).

---

## 14. Operating guidelines for the agent

1. **Read order:** `TASK.md` → `ROADMAP.md` → `docs/upstream/sentinel-model-roadmap.md` → the system and integration roadmaps.
2. **Work phase by phase.** Do not start phase *n+1* until the gate for phase *n* passes. A failed gate means fix, not skip.
3. **Evidence over assertion.** Never report a number you did not produce with a committed script. Never fabricate or "round up" results. If something could not be run (no GPU, no network, dataset path missing), say so and record the fallback.
4. **Honesty on the target.** Report the achieved F1 under the frozen protocol. Do not alter splits, labels, or thresholds after seeing test results to approach 97–99%.
5. **Test discipline.** Write tests with the code; `make check` green before every merge. Unit, property, leakage, conformance and serving tests are all required.
6. **Single source of truth for shared logic.** The bin accumulator, tensor builder, verdict mapping and schema validation are shared by offline and serving code; do not fork them.
7. **Contract discipline.** No silent divergence. Open a CR entry instead.
8. **Scope discipline.** Stretch items start only after the P8 gate, or per the cut-list in ROADMAP.
9. **Blockers.** Write `reports/BLOCKER-<id>.md`, commit, stop dependent work, and surface it in the final report.
10. **Keep `STATUS.md` current** (current phase, checklist, last tag, open issues) so work can resume in a new session.
11. **Don't touch other tracks** (system pipeline, integration) or the parent repo.
12. **Dataset etiquette:** cite CIC-DDoS2019 (Sharafaldin et al., 2019) in `MODEL_CARD.md`; do not commit dataset content.

---

## 15. Acceptance checklist (Definition of Done)

- [ ] `contract/CONTRACT.md` vendored with recorded SHA-256; JSON Schemas generated; conformance suite green on the built container (O1)
- [ ] `reports/P1_dataset_audit.md` complete, verdict recorded, `data/MANIFEST.json` committed (O2)
- [ ] Leakage tests green; split indices hashed; protocol frozen (`protocol-freeze`)
- [ ] A0, A1, A2, A3 results on identical splits (`reports/P5_baselines.md`)
- [ ] MobileNetV2 and ViT-Tiny (or documented fallback) trained, 3 seeds, selected on validation only
- [ ] Final test report generated once after `config-freeze`: P-A and P-B, window-level and flow-level metrics, CIs, per-attack-type recall, delay and flip rate (O3–O5)
- [ ] Ablations 1–8 completed or explicitly cut per the cut-list (with DECISIONS entries)
- [ ] Calibration done; `thresholds.json` stored with the artifact; `confidence` rule tested
- [ ] ONNX export with torch↔ONNX parity; serving image has no torch dependency
- [ ] Offline↔service parity (O7) demonstrated on ≥ 1 hour of real test-split data
- [ ] Latency report (`reports/P8_latency.md`): p50/p95/p99 per tier at 100/500/1000 req/s; vs. budget (O6)
- [ ] Edge-case tests (§10.5) green; malformed requests proven not to mutate state
- [ ] Docker image built from tag `v0.1.0`, `model_version` correct in responses, runs side-by-side on another port (O9)
- [ ] `MODEL_CARD.md`, `HANDOFF.md`, `DATA_SPEC.md`, `DECISIONS.md`, `EVALUATION.md`, `README.md`, `CHANGELOG.md` complete (O10)
- [ ] `STATUS.md` shows all phases done; all tags present; `main` green

---

## 16. Risk register

| ID | Risk | Mitigation |
|---|---|---|
| R1 | No usable timestamp in the precleaned CSV | P1 check A3; block B1; do not fabricate a time axis |
| R2 | Imbalance direction differs from the brief | P1 A4/A11; direction-agnostic metrics (D5) |
| R3 | Inflated scores from leakage / easy dataset | blocked splits with gaps, P-B, leakage tests, report both |
| R4 | Train/serve skew: CICFlowMeter flows ≠ system's flow generator | D7 config, HANDOFF notes, Integration Steps 1 and 3 re-evaluation |
| R5 | Stateful service breaks under multi-stream or multi-worker use | single worker, per-stream instances, CR-4 |
| R6 | Fast-tier latency miss | per-bin cache (D8), ONNX, remedy ladder in P8 |
| R7 | DWT shift variance causes verdict flicker | flip-rate metric, SWT ablation, optional offset averaging in deep tier |
| R8 | Data volume / memory | Parquet, polars lazy, contiguous-span reduction only |
| R9 | Pretrained weights unavailable offline | scratch fallback logged; M-floor still required |
| R10 | Window-level verdict misused as per-flow block trigger | D2, MODEL_CARD, HANDOFF |
| R11 | Few benign windows → wide CIs | B3 check, report CIs, boundary-window analysis |
| R12 | Time budget overrun | cut-list in ROADMAP; must-not-cut list |

---

## 17. Contract change requests (proposed — NOT implemented unless approved)

Track in `docs/CONTRACT_CHANGE_REQUESTS.md`; the contract is changed only via the system track.

| ID | Proposal | Reason |
|---|---|---|
| CR-1 | Clarify `timestamp` semantics (flow start vs. end/emit) | D7 |
| CR-2 | Optional `warmup: boolean` in the response | cold-start signalling |
| CR-3 | Optional per-flow packet-IAT / length statistics in `features` | enables true packet-level signals (D1) |
| CR-4 | Optional `stream_id` in the request | live and offline streams sharing one instance (D3) |
| CR-5 | Pin the HTTP status code for malformed requests | conformance consistency |
| CR-6 | Clarify `byte_count`/`packet_count` (both directions? flow-timeout rules) | train/serve skew (R4) |
