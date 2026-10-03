# Architecture Decision Records (ADRs)

| Context | Options | Decision | Evidence |
|---|---|---|---|
| P1: Window feasibility audit initially found 0 benign windows due to binary presence (>0 attack flows) across 256s blocks in heavily attack-dominated CIC-DDoS2019 dataset. | 1. Shrink window size T/Δ.<br>2. Adhere strictly to TASK §8.3 trailing-tail majority fraction τ≥0.5 & min 5 attack flows.<br>3. Inject synthetic flows. | Option 2: Implement strict TASK §8.3 τ-tail classification for window labeling. | 125 benign windows and 106 attack windows found across 231 total 256s blocks. Resolves BLOCKER B3 without shrinking window size or altering dataset. |

