# ROADMAP.md — W-MSTSE Detection Model

**Project:** Cybersecurity Sentinel — AI-Based Network Traffic Analysis and Automated Response System
**Model:** `wmstse` · **Repo root:** `<project_dir>/wmstse/` · **Rules and specs:** `TASK.md` (authoritative for *what*; this file is *order and gates*)

3-week scope, nine phases (P0–P8). Each phase ends in a **gate**: do not start the next phase until the gate passes.

---

## How to run every phase (the loop)

1. `git switch main && git switch -c phase/P<n>-<slug>`
2. Implement the tasks, writing tests alongside the code. Commit small and often (Conventional Commits, scope = phase).
3. `make check` green.
4. Write `reports/gates/P<n>.md`: git SHA, commands run, key numbers, checklist ticks, deviations, open issues.
5. Update `STATUS.md`, `CHANGELOG.md`, and `docs/DECISIONS.md` for any deviation.
6. `git switch main && git merge --no-ff phase/P<n>-<slug>`
7. `git tag -a <tag> -m "<gate summary>"`

If the gate fails: fix and re-run the gate. If blocked: write `reports/BLOCKER-<id>.md`, commit, stop dependent work, report.

---

## Timeline

| Week | Days | Phase | Maps to model-roadmap step | Tag |
|---|---|---|---|---|
| **1 — Data & preprocessing** | 1 | **P0** Scaffold, VC, contract adoption, stub | Step 1 | `phase-P0-contract-stub` |
| | 1–2 | **P1** Dataset validity audit | Step 2 | `phase-P1-audit` |
| | 2–4 | **P2** Flow stream, binning, windows, splits | Step 2 | `phase-P2-stream-windows` |
| | 4–5 | **P3** Wavelet decomposition | Step 4/5 analogue | `phase-P3-wavelet` |
| **2 — Tensor generation** | 6–8 | **P4** Entropy tensors + QA + probe | Step 4/5 analogue | `phase-P4-tensors` |
| | 8–10 | **P5** Baselines + evaluation harness + protocol freeze | Step 3 | `phase-P5-baselines`, `protocol-freeze` |
| **3 — Model training & delivery** | 11–12 | **P6** Train vision models | Step 4/5 analogue | `phase-P6-training` |
| | 13 | **P7** Calibration, freeze, final evaluation, ablations | Step 4 evaluation | `config-freeze`, `phase-P7-evaluation` |
| | 14–15 | **P8** Serving, latency, packaging, docs, release | Step 6 | `phase-P8-release`, `v0.1.0` |

---

## P0 — Scaffold, Version Control, Contract Adoption (Day 1)

**Goal:** A versioned repo and a service speaking the exact contract before any real model exists.

**Tasks**
1. Create `<project_dir>/wmstse/`. `git init -b main` (or resume per TASK §12 if `.git` exists). Add `.gitignore` (data, interim, tensors, checkpoints, `.venv`, caches), `.pre-commit-config.yaml` (ruff), `pyproject.toml` + lock file, `Makefile`.
2. Copy `TASK.md` and `ROADMAP.md` to the repo root if they are elsewhere. Vendor the three upstream roadmaps unchanged into `docs/upstream/`. First commit: `docs: vendor upstream roadmaps and task files`.
3. **Contract adoption:** copy `CONTRACT.md` from the system track (`SYSTEM_CONTRACT`) into `contract/` unchanged; record its SHA-256. If it doesn't exist, build it verbatim from the schema block in `sentinel-model-roadmap.md`, mark it `VENDORED-UNVERIFIED` in its header, and flag it. Generate `contract/schemas/request.json` and `response.json`, tested against example payloads.
4. Open `docs/CONTRACT_CHANGE_REQUESTS.md` with CR-1…CR-6 from TASK §17 (status: proposed).
5. **Stub service** (FastAPI): `POST /infer`, deterministic verdict from a hash of `flow_id`, schema-correct, `model_version = "wmstse-stub-0.0.0"`.
6. **Conformance suite:** vendor the system track's tests if available; add ours: valid request → schema-valid response; malformed (missing field, wrong type, bad `tier`, bad timestamp) → clean 4xx JSON; `flow_id` echoed; `confidence ∈ [0,1]`; non-empty `model_version`; `latency_ms ≥ 0`; fast-tier latency check.
7. Write `README.md` skeleton, `STATUS.md`, `CHANGELOG.md`, `docs/DECISIONS.md` (empty ADR log).
8. Write `tools/make_synthetic_stream.py` (benign background + injected volumetric bursts) — tests must run without the real dataset.

**Deliverables:** repo skeleton, vendored docs and contract, stub service, conformance suite, synthetic stream generator.

**Gate P0**
- [ ] `make check` green; conformance suite passes against the stub
- [ ] Contract SHA-256 recorded in `reports/gates/P0.md`; open contract questions listed (timestamp semantics, `byte_count`/`packet_count` meaning, protocol vocabulary, error status code)
- [ ] Tag `phase-P0-contract-stub`

---

## P1 — Dataset Validity Audit (Days 1–2)

**Goal:** Establish whether the precleaned CIC-DDoS2019 CSV can support a time-series method. **Validate; do not clean.**

**Tasks**
1. Inventory `DATASET_DIR`: names, sizes, row counts, SHA-256 → `data/MANIFEST.json`.
2. Convert CSV → Parquet in `data/interim/` (chunked/lazy; raw files untouched). Normalize column names through an explicit rename map.
3. Run audit checks **A1–A11** (TASK §7.2) via `make audit`, producing `reports/P1_dataset_audit.md` and `reports/p1_audit.json`.
4. Check every B-condition (TASK §7.3). On B1/B2/B3: write the blocker report and stop.
5. Measure imbalance at flow level and at window level for the default (Δ, T) and the grid (D5). State plainly whether the brief's imbalance assumption holds.
6. Record per-attack-type time ranges (segments) — P2's splits depend on them.

**Deliverables:** audit report with verdict; machine-readable audit JSON; data manifest; Parquet conversion.

**Gate P1**
- [ ] Verdict is `PASS` or `PASS-WITH-CAVEATS` with every caveat listed; no unresolved `BLOCK`
- [ ] Timestamp usable (A3) and contract-mapping coverage ≥ 99.9% (A9)
- [ ] Any filter applied is logged with counts in `DECISIONS.md`; raw files unchanged (hash re-check)
- [ ] Tag `phase-P1-audit`

**Pitfalls:** assuming column names; microsecond vs. millisecond durations; timezone shifts across files; treating the benign-majority assumption as fact.

---

## P2 — Flow Stream, Binning, Windows, Splits (Days 2–4)

**Goal:** A canonical, contract-valid flow stream and a leakage-safe set of labelled windows.

**Tasks**
1. `docs/DATA_SPEC.md`: CSV→contract mapping table, units, protocol vocabulary, timestamp semantics decision (D7), empty-bin conventions, label definition.
2. Build the canonical `FlowRecord` stream (TASK §8.1), sorted by event time with stable tie-break.
3. **Contract validity:** convert records to contract requests and validate against `contract/schemas/` (full pass, not a sample — report the failure count, which must be 0 or explained).
4. Implement binning twice, with a parity test: **vectorized** (polars/NumPy) for offline, **incremental `BinAccumulator`** (sums only, lateness-aware) for serving. Channels per TASK §8.2.
5. Windowing + labels (TASK §8.3): `T`, stride, trailing-tail label rule, `attack_fraction`, `attack_type`, boundary-window flag.
6. **Splits** P-A and P-B (TASK §9.1): segment detection, 70/15/15 blocks with gaps, drop gap-overlapping windows; write index files + hashes.
7. Tests: hand-built mini streams with known bin values; property tests (sum of bins = sum of flows, order-invariance within lateness, no division by zero); **leakage tests** (no flow/window overlap across splits); vectorized↔incremental parity.
8. Window/segment stats table per split (counts per class, per attack type).

**Deliverables:** `DATA_SPEC.md`, stream builder, binning (both forms), windowing, split indices, tests, stats table.

**Gate P2**
- [ ] 100% of records contract-schema-valid
- [ ] Parity test (vectorized vs. incremental) passes on synthetic and ≥ 1 hour of real data
- [ ] Leakage tests green
- [ ] Every split has ≥ 30 windows of each class (else escalate B3 — adjust (Δ, T) within the grid or add contiguous data)
- [ ] Tag `phase-P2-stream-windows`

**Pitfalls:** Python loops over tens of millions of rows; per-window normalization that leaks; sorting by row order instead of event time; windows straddling split boundaries.

---

## P3 — Wavelet Decomposition (Days 4–5)

**Goal:** A tested decomposition layer, validated on synthetic and real signals.

**Tasks**
1. `wavelet/decompose.py`: `decompose(signal, wavelet, level, mode, kind)` returning `level + 1` bands (DWT) or equal-length bands (SWT). Guards: `level ≤ pywt.dwt_max_level(T, dec_len)` and `T % 2**level == 0`; fail loudly.
2. Tests: perfect reconstruction (tolerance 1e-8); energy preservation (orthogonal wavelets, `periodization`); synthetic signals (sine, impulse train, white noise, step) land energy in expected bands.
3. Real-data sanity: per-band energy for benign vs. attack windows (box plots → `reports/figures/`); verify no degenerate (all-zero/constant) bands.
4. Implement SWT behind the same interface (needed for P7 ablation 4).
5. Fix the candidate grid (wavelet × level) — small, in `configs/ablations/`.

**Deliverables:** decomposition module, tests, sanity figures, SWT variant.

**Gate P3**
- [ ] Reconstruction/energy tests pass; level guard tested
- [ ] Band-energy figures show benign/attack separation in at least some bands (or the absence is recorded in DECISIONS and investigated before P4)
- [ ] Tag `phase-P3-wavelet`

---

## P4 — Entropy Tensors (Days 6–8)

**Goal:** Tensors `X ∈ R^{C×B×T_out}` that demonstrably carry signal, built identically offline and online.

**Tasks**
1. `entropy/fit_edges.py`: per-(channel, band) quantile bin edges from **training windows only** → `artifacts/preproc/entropy_edges.npz` + hash. Same for per-channel normalization stats.
2. `entropy/rolling.py` and `entropy/tensor.py` per TASK §8.5 (rolling entropy of coefficient magnitudes, normalization by `log2 K`, resample to `T_out`, stack).
3. Tensor build CLI → `data/tensors/<split>/<cfg-hash>.npz` (`X float32`, `y`, metadata) with a manifest (config hash, git SHA, shapes).
4. **Tensor QA:** no NaN/Inf; values in range; per-(channel, band) variance > 0; mean "spectrograms" per class and per attack type (→ `reports/figures/`); build time per window.
5. **Separability probe (A3):** flatten tensors → XGBoost/logistic on train → validation. Compare with quick A1/A2 proxies. If the probe doesn't beat A1 on validation: **stop and investigate** the tensor design (bins K, span, channels, wavelet, labels) before any deep training. At most two logged design iterations.
6. Online/offline parity test for the tensor builder (stream replay vs. batch).
7. Document effective time span per band in `DATA_SPEC.md`.

**Deliverables:** fitted preprocessing artifacts, tensor datasets with manifests, QA report, probe results, parity test.

**Gate P4**
- [ ] QA clean; parity test green; preprocessing provably fit on train only
- [ ] Probe (A3) ≥ A1 proxy on validation — or investigation documented and resolved
- [ ] Tag `phase-P4-tensors`

---

## P5 — Baselines, Evaluation Harness, Protocol Freeze (Days 8–10)

**Goal:** Trustworthy comparators and a frozen protocol before the novel model is trained.

**Tasks**
1. `eval/metrics.py`: window-level and flow-level metrics, PR-AUC both ways, MCC, block-bootstrap CIs, streaming metrics (delay, false-positive windows per benign hour, flip rate), per-attack-type recall.
2. **A0** per-flow RF/XGBoost on contract-available features (flow-level metrics + window aggregation).
3. **A1** prior art: single-scale entropy (no wavelet): threshold detector tuned on validation + XGBoost on entropy statistics.
4. **A2** window statistics → XGBoost.
5. Run all baselines on P-A and P-B using the P2 split indices; selection on validation only.
6. Write `configs/eval_protocol.yaml` (split hashes, metric list, seeds, bootstrap settings) and tag **`protocol-freeze`**. After this tag the protocol may not change without a DECISIONS entry.
7. `reports/P5_baselines.md`: results table with CIs. If A0/A2 already score ≈ 100% under P-A, say so explicitly — it means the split is easy, and P-B and boundary windows carry more information.

**Deliverables:** harness, baseline results, frozen protocol.

**Gate P5**
- [ ] Baselines reproducible from `make baselines`
- [ ] Leakage tests still green; protocol frozen
- [ ] Tags `phase-P5-baselines`, `protocol-freeze`

---

## P6 — Train Vision Models (Days 11–12)

**Goal:** Selected W-MSTSE model(s) trained on the frozen protocol, selected on validation only.

**Tasks**
1. Data loaders, class weighting, input mapping options (resize vs. row repetition), allowed augmentations only.
2. Models: MobileNetV2 (pretrained), ViT-Tiny (pretrained), tiny CNN (scratch floor). If pretrained weights are unavailable offline, train from scratch and log it.
3. Training loop: AdamW, cosine schedule, early stopping on validation macro-F1, deterministic seeds, mixed precision if GPU present, curves saved as CSV + PNG.
4. 3 seeds per candidate; report mean ± std on validation.
5. Select backbone/config **on validation** (macro-F1; latency as tie-break). Do not look at test.
6. Export the chosen checkpoint to ONNX now (early) and check torch↔ONNX parity and CPU latency for a single window — if hopeless, reconsider the backbone before P7.

**Deliverables:** checkpoints (manifested), training logs, validation table, ONNX export + parity check.

**Gate P6**
- [ ] Selected model beats the A1 proxy on validation; M-floor result recorded for context
- [ ] Re-running with the same seed reproduces validation metrics within tolerance
- [ ] ONNX parity ≤ 1e-3; single-window CPU inference time recorded
- [ ] Tag `phase-P6-training`

---

## P7 — Calibration, Freeze, Final Evaluation, Ablations (Day 13)

**Goal:** Calibrated verdicts, a frozen configuration, and one honest test-set report.

**Tasks**
1. **Calibration:** temperature scaling on validation; choose `τ_low`, `τ_high` per TASK §10.4; save `thresholds.json`; test the `confidence` mapping (monotonic, in `[0,1]`).
2. **Ablations** (TASK §9.4), OFAT, ≥ 3 seeds, evaluated on **validation** for decisions. Apply the **DWT-vs-SWT rule**: switch the default to SWT only if it improves validation macro-F1 by ≥ 0.005 with non-overlapping CI **or** reduces the 1-bin-shift flip rate by ≥ 50% at no more than 0.005 macro-F1 loss; log the decision either way.
3. **Freeze:** commit the final config, tag **`config-freeze`**.
4. **Final report** via `eval/final_report.py` — run once: P-A and P-B, window-level and flow-level, CIs, per-attack-type recall, boundary windows, streaming delay and flip rate; all baseline and ablation rows get their test column from this single run.
5. Robustness curves (jitter, bin-phase, flow dropout, out-of-order) — reported, not gated.
6. Failure analysis: inspect false positives/negatives (tensors, attack types, boundary windows).
7. Optional stretch (only if time remains): **S1** leave-one-attack-type-out; **S2** synthetic multi-vector overlay (clearly labelled synthetic; never mixed into headline metrics).
8. `reports/EVALUATION.md`: side-by-side table (A0, A1, A2, W-MSTSE, ablations) in the same shape the integration track will use for its variant comparison; honest statement on the 97–99% target; limits and failure modes.

**Deliverables:** calibrated thresholds, frozen config, final report, ablation table, `EVALUATION.md`.

**Gate P7**
- [ ] Every number in `EVALUATION.md` regenerates from a committed script at the recorded SHA
- [ ] Test split touched only after `config-freeze` (git history proves it)
- [ ] Novelty claim stated as supported / not supported / inconclusive, with CIs
- [ ] Tags `config-freeze`, `phase-P7-evaluation`

---

## P8 — Serving, Latency, Packaging, Docs, Release (Days 14–15)

**Goal:** A swappable, versioned, documented container.

**Tasks**
1. **Serving state** (`serve/state.py`): event-time ring buffer on the shared `BinAccumulator`, lateness handling, closed-bin logic, dedupe LRU, warm-up, regression-reset policy, thread safety, single worker.
2. **Inference** (`serve/infer.py`, `serve/verdict.py`): ONNX Runtime; background worker publishes the per-bin cached verdict atomically; `fast` reads the cache; `deep` recomputes synchronously (optional offset averaging); shared verdict mapping; `latency_ms`; `model_version` from build arg.
3. **Parity:** replay ≥ 1 hour of real test-split data through the HTTP service; compare per-window tensor (≤ 1e-5) and `p_attack` (≤ 1e-4) with offline.
4. **Conformance + edge cases:** run the full suite from P0 against the real service, plus every row of TASK §10.5; prove malformed requests do not mutate state.
5. **Latency & load** (`tools/loadtest.py` replaying the CSV stream at 100/500/1000 req/s): p50/p95/p99 per tier, memory, CPU → `reports/P8_latency.md`. If fast-tier p99 misses the budget, apply this **remedy ladder** in order, re-measuring each time and checking accuracy: ONNX thread settings → cache-path tuning → smaller `input_size` → smaller backbone → int8/fp16 quantization (accuracy re-check) → distilled student (stretch). Record the outcome; if still missed, state the achievable budget for the integration track's decision.
6. **Docker:** multi-stage, non-root, CPU-only ONNX Runtime image; `MODEL_VERSION` build arg; `PORT` env; fails on dirty tree; tagged `wmstse:<semver>`. Run a fresh container → conformance green; run side-by-side with the stub on another port.
7. **Docs:** `MODEL_CARD.md` (intended use, data, metrics, limits, window-level semantics, failure modes, dataset citation), `HANDOFF.md` (TASK §10.8), `README.md` (build, run, point the pipeline at the endpoint, run conformance), finalize `DECISIONS.md` and `CHANGELOG.md`.
8. **Release:** write `artifacts/release/<model_version>/MANIFEST.json`; merge to `main`; tag `phase-P8-release` and `v0.1.0`; `model_version = wmstse-0.1.0+<sha7>`.

**Deliverables:** serving code, container image, latency report, docs, release artifact and manifest.

**Gate P8 (= final acceptance, TASK §15)** — all checkboxes ticked; `STATUS.md` shows complete.

---

## Cut-list (use only if a phase overruns its time box by > 50%)

Cut in this order: (1) stretch items S1–S2, robustness curves → (2) ViT-Tiny (keep MobileNetV2 + floor CNN) → (3) wavelet-family and `K`/span ablations (keep ablations 1, 2, 4) → (4) seeds 3 → 2 → (5) P-B secondary analyses. Log every cut in `DECISIONS.md`.

**Must NOT be cut:** contract conformance · dataset audit · leakage-safe splits and tests · baselines A0/A1/A2 · offline↔service parity · latency measurement · `MODEL_CARD` and `HANDOFF` · honest reporting of results.

## Stretch backlog (after P8 only)
S1 leave-one-attack-type-out · S2 synthetic multi-vector overlays · S3 SWT as default (if P7 rule triggers) · S4 distilled student for the fast tier · S5 attack-family head · S6 Kafka transport adapter (contract's optional upgrade).

---

## Appendix A — Commit and tag examples

```
feat(P2): add incremental BinAccumulator with lateness handling
test(P2): leakage checks for blocked temporal splits
fix(P4): fit entropy edges on train indices only
docs(P1): dataset audit report and verdict
perf(P8): move tensor rebuild off the request path
chore(P0): vendor CONTRACT.md (sha256 recorded)

git tag -a phase-P3-wavelet -m "P3 gate: reconstruction/energy tests pass; level guard; band-energy figures"
```

## Appendix B — `reports/gates/P<n>.md` template

```
# Gate P<n> — <name>
Git SHA: <sha>      Branch: phase/P<n>-<slug>      Tag: <tag>
Commands run: <make targets / scripts>
Key numbers: <metrics with CIs, counts, timings>
Checklist: [x] ... [x] ...
Deviations (see DECISIONS.md): <list or none>
Open issues / risks: <list or none>
```

## Appendix C — `STATUS.md` template

```
Current phase: P<n>      Last tag: <tag>      main green: yes/no
Done: P0 ✔ P1 ✔ ...
In progress: <tasks>
Blockers: <none | BLOCKER-id>
Next action: <one line>
```
