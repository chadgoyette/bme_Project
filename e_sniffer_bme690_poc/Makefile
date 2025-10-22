PYTHON ?= python

.PHONY: collector dataprep train live detector workflow test lint

collector:
	$(PYTHON) -m collector.collect

dataprep:
	$(PYTHON) -m dataprep.build --logs-root ./logs --out ./prepared --drop-unstable

train:
	$(PYTHON) -m training_cnn.train --prepared-dir ./prepared --out ./models/cnn_$$(date +%Y%m%d_%H%M) --epochs 40 --batch-size 32 --learning-rate 0.001 --val-fraction 0.2 --patience 5

live:
	$(PYTHON) -m live_test.app

detector:
	$(PYTHON) -m detector.app

workflow:
	$(PYTHON) -m workflow.app

test:
	$(PYTHON) -m pytest
