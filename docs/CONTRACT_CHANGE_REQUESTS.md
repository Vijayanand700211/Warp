# Contract Change Requests

| ID | Proposal | Reason | Status |
|---|---|---|---|
| CR-1 | Clarify `timestamp` semantics (flow start vs. end/emit) | D7 | proposed |
| CR-2 | Optional `warmup: boolean` in the response | cold-start signalling | proposed |
| CR-3 | Optional per-flow packet-IAT / length statistics in `features` | enables true packet-level signals (D1) | proposed |
| CR-4 | Optional `stream_id` in the request | live and offline streams sharing one instance (D3) | proposed |
| CR-5 | Pin the HTTP status code for malformed requests | conformance consistency | proposed |
| CR-6 | Clarify `byte_count`/`packet_count` (both directions? flow-timeout rules) | train/serve skew (R4) | proposed |
