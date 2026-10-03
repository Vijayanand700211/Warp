import random
import json
from datetime import datetime, timedelta

def main():
    # Generate benign background
    t0 = datetime.fromisoformat("2026-10-03T10:00:00+00:00")
    
    with open("data/synthetic_stream.jsonl", "w") as f:
        for i in range(1000):
            dt = t0 + timedelta(seconds=i * 0.1)
            f.write(json.dumps({
                "flow_id": f"flow-{i}",
                "timestamp": dt.isoformat(),
                "duration_ms": random.uniform(10, 500),
                "byte_count": random.randint(100, 10000),
                "packet_count": random.randint(5, 50),
                "protocol": "TCP",
                "label": "benign"
            }) + "\n")
            
        # Inject attack burst
        for i in range(1000, 1500):
            dt = t0 + timedelta(seconds=100 + i * 0.01) # fast burst
            f.write(json.dumps({
                "flow_id": f"flow-{i}",
                "timestamp": dt.isoformat(),
                "duration_ms": random.uniform(1, 10),
                "byte_count": random.randint(64, 128),
                "packet_count": random.randint(1, 3),
                "protocol": "UDP",
                "label": "attack"
            }) + "\n")

if __name__ == "__main__":
    main()
