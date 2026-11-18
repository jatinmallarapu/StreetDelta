# The demo is local and runs without model weights or API tokens.
.PHONY: up serve test eval ingest

up:
	docker compose up --build

serve:
	uvicorn streetdelta.api:app --host 127.0.0.1 --port 8000

test:
	python -m pytest -q

eval:
	python -m eval.metrics

ingest:
	python -m streetdelta.mapillary --out runs/mapillary.parquet
