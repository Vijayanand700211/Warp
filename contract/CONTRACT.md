# CONTRACT.md (VENDORED-UNVERIFIED)

**REQUEST SCHEMA**
```json
{
  "flow_id": "string",
  "tier": "fast" | "deep",
  "features": {
    "duration_ms": "number",
    "byte_count": "number",
    "packet_count": "number",
    "protocol": "string",
    "entropy": "number",
    "ja3_hash": "string | null",
    "dns_before_ip": "boolean"
  },
  "timestamp": "ISO8601"
}
```

**RESPONSE SCHEMA**
```json
{
  "flow_id": "string",
  "verdict": "benign" | "suspicious" | "malicious",
  "confidence": "number",
  "model_version": "string",
  "latency_ms": "number"
}
```
