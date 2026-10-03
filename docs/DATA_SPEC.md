# Data Specification (DATA_SPEC.md)

This document defines the mapping between the raw CIC-DDoS2019 dataset CSV columns and the canonical `FlowRecord` / API Contract used by the W-MSTSE streaming inference system.

## 1. CSV to Contract Mapping Table

The source files contain many columns. We extract and compute the following to form a valid contract request schema (`contract/schemas/request.json`).

| Source CSV Column | Contract Field (`features.*` unless noted) | Transformation / Notes |
| :--- | :--- | :--- |
| `Flow ID` | `flow_id` (Root) | Passed directly as string. Used for deduplication. |
| `Timestamp` | `timestamp` (Root) | Parsed from format (`%Y-%m-%d %H:%M:%S.%f` or similar). Represented in ISO 8601 format. |
| `Flow Duration` | `duration_ms` | CIC-DDoS2019 reports flow duration in microseconds. Converted to milliseconds (`duration_ms = Flow Duration / 1000`). |
| `Total Length of Fwd Packets` + `Total Length of Bwd Packets` | `byte_count` | Sum of forward and backward payload bytes. |
| `Total Fwd Packets` + `Total Backward Packets` | `packet_count` | Sum of forward and backward packets. |
| `Protocol` | `protocol` | Numeric ID from CSV mapped to vocabulary string (e.g., 6 → "TCP", 17 → "UDP", 0 → "HOPOPT"). Unmapped values mapped to "UNKNOWN". |
| N/A | `entropy` | Not provided in CSV. Set to `0.0` or `null` in simulated requests if unavailable. |
| N/A | `ja3_hash` | Not provided in CSV. Set to `null`. |
| N/A | `dns_before_ip`| Not provided in CSV. Set to `false`. |
| `Label` | `label_type` (Metadata) | Internal training metadata (e.g. "BENIGN", "Syn"). |
| `Label` | `label_binary` (Metadata) | Derived: `BENIGN` → 0 (benign), else → 1 (attack). |

## 2. Units

*   **Time/Duration:** Milliseconds (`ms`) for flow duration.
*   **Size:** Bytes for lengths, count for packets.
*   **Bin Width (Δ):** Seconds (e.g., 1.0s).
*   **Rates:** 
    *   `rate_pkts` = `log1p(sum_packets)`
    *   `rate_flows` = `log1p(n_flows)`
*   **Length Analogue:** `len` = `sum_bytes / sum_packets`

## 3. Protocol Vocabulary

The `Protocol` field in the dataset uses IANA Protocol Numbers. We map them to the following vocabulary:
*   `0`: "HOPOPT"
*   `6`: "TCP"
*   `17`: "UDP"
*   *(Any other number)*: "UNKNOWN" (or specific IANA names if needed, but TCP/UDP cover >99% of W-MSTSE traffic).

## 4. Timestamp Semantics (Decision D7)

**Decision D7:** The reference timestamp for a flow is the **Start Time**.
Since CIC-DDoS2019 logs the start time in the `Timestamp` column and provides `Flow Duration`, we use `Timestamp` directly for binning into the stream. Late-arriving flows (end of flow > bin close) are handled using the `lateness_bins` parameter in the model serving tier. 

## 5. Empty-Bin Conventions

If a time bin $\Delta$ (e.g., 1 second) has zero flows:
*   `n_flows` = 0
*   `sum_bytes` = 0
*   `sum_packets` = 0

For the multi-channel tensor:
*   `len` = 0.0 (explicit convention for empty bins to avoid `0/0` NaN).
*   `rate_pkts` = `log1p(0)` = 0.0
*   `rate_flows` = `log1p(0)` = 0.0

Empty bins are valid zeros in the W-MSTSE stream representation and represent silent periods in network traffic.

## 6. Label Definitions and Windowing

As per the specification (TASK.md §8.3):
*   **Window Label:** A window $W$ is labeled as `attack` if and only if the attack-flow fraction in the *trailing* `label_tail_bins` (16 bins) $\ge \tau$ (0.5) **and** total attack flows in that tail $\ge$ `min_attack_flows` (5).
*   **Boundary Windows:** Windows with $0 < \text{attack\_fraction} < 1$ are retained and reported separately as "boundary windows".

## 7. Effective Time Span per Band (Wavelet)

The model computes rolling Shannon entropy over the wavelet coefficients. With $B$ bands, the coarse bands integrate over longer time spans natively.
Assuming `db4` wavelet and max level $L=4$ (yielding 5 sub-bands: $cA_4, cD_4, cD_3, cD_2, cD_1$):
*   High-frequency detail band ($cD_1$) integrates over short spans (rapid changes).
*   Low-frequency approximation band ($cA_4$) integrates over the entire support of the coarse scale (identifying long-term shifts in traffic).
The exact rolling window $w_j = \max(8, \text{round}(\text{span} / 2^j))$ scales down for coarser bands to maintain a balanced effective time span across the tensor.
