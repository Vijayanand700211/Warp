.PHONY: check audit streams tensors baselines train eval serve loadtest docker reproduce-small

check:
	pytest tests/

audit:
	python src/wmstse/data/audit.py

streams:
	python src/wmstse/data/stream.py

tensors:
	python src/wmstse/entropy/tensor.py

baselines:
	python src/wmstse/eval/baselines.py

train:
	python src/wmstse/models/train.py

eval:
	python src/wmstse/eval/final_report.py

serve:
	uvicorn src.wmstse.serve.app:app --host 0.0.0.0 --port 8000

loadtest:
	python tools/loadtest.py

docker:
	docker build -t wmstse:0.1.0 -f docker/Dockerfile .

reproduce-small:
	python tools/make_synthetic_stream.py
	make check
