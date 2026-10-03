from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, Field
import hashlib
from typing import Literal, Optional

app = FastAPI(title="W-MSTSE Stub Service")

class Features(BaseModel):
    duration_ms: float
    byte_count: float
    packet_count: float
    protocol: str
    entropy: float
    ja3_hash: Optional[str]
    dns_before_ip: bool

class InferRequest(BaseModel):
    flow_id: str
    tier: Literal["fast", "deep"]
    features: Features
    timestamp: str

class InferResponse(BaseModel):
    flow_id: str
    verdict: Literal["benign", "suspicious", "malicious"]
    confidence: float
    model_version: str
    latency_ms: float

def fake_verdict(flow_id: str) -> str:
    h = int(hashlib.md5(flow_id.encode('utf-8')).hexdigest(), 16)
    rem = h % 10
    if rem < 8:
        return "benign"
    elif rem == 8:
        return "suspicious"
    else:
        return "malicious"

@app.post("/infer", response_model=InferResponse)
async def infer(req: InferRequest):
    # Deterministic fake verdict
    verdict = fake_verdict(req.flow_id)
    confidence = 0.95 if verdict != "suspicious" else 0.5
    
    return InferResponse(
        flow_id=req.flow_id,
        verdict=verdict,
        confidence=confidence,
        model_version="wmstse-stub-0.0.0",
        latency_ms=1.5 # fake latency
    )
