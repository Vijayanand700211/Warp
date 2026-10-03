import pytest
from fastapi.testclient import TestClient
from src.wmstse.serve.app import app
import time

client = TestClient(app)

def test_valid_request():
    payload = {
        "flow_id": "test-flow-1",
        "tier": "fast",
        "features": {
            "duration_ms": 100,
            "byte_count": 1024,
            "packet_count": 10,
            "protocol": "TCP",
            "entropy": 4.5,
            "ja3_hash": "a1b2c3d4",
            "dns_before_ip": True
        },
        "timestamp": "2026-10-03T10:00:00Z"
    }
    
    t0 = time.time()
    response = client.post("/infer", json=payload)
    t1 = time.time()
    
    assert response.status_code == 200
    data = response.json()
    assert data["flow_id"] == "test-flow-1"
    assert data["verdict"] in ["benign", "suspicious", "malicious"]
    assert 0 <= data["confidence"] <= 1
    assert data["model_version"] != ""
    assert data["latency_ms"] >= 0
    
    # fast tier latency check (<50ms for the stub itself)
    # The requirement is that fast tier should be < 50ms, let's just assert test time < 50ms (or 100ms accounting for overhead)
    assert (t1 - t0) < 0.1

def test_malformed_request_missing_field():
    payload = {
        "flow_id": "test-flow-2",
        "tier": "fast",
        "features": {
            "duration_ms": 100,
            # missing byte_count
        },
        "timestamp": "2026-10-03T10:00:00Z"
    }
    response = client.post("/infer", json=payload)
    assert response.status_code == 422 # FastAPI default validation error

def test_malformed_request_bad_tier():
    payload = {
        "flow_id": "test-flow-3",
        "tier": "medium", # invalid
        "features": {
            "duration_ms": 100,
            "byte_count": 1024,
            "packet_count": 10,
            "protocol": "TCP",
            "entropy": 4.5,
            "ja3_hash": None,
            "dns_before_ip": False
        },
        "timestamp": "2026-10-03T10:00:00Z"
    }
    response = client.post("/infer", json=payload)
    assert response.status_code == 422
