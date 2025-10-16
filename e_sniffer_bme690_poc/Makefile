PYTHON ?= python

.PHONY: collector dataprep train live detector workflow test lint

collector:
	$(PYTHON) -m collector.collect

dataprep:
	$(PYTHON) -m dataprep.build --data-root ./data --out ./prepared --window-sec 600 --stride-sec 60 --baseline-sec 60 --resample-hz 1

train:
	$(PYTHON) -m training.train --in ./prepared/features.parquet --out ./models/exp_$$(date +%Y%m%d_%H%M) --group-col specimen_id --model rf --cv-folds 5

live:
	$(PYTHON) -m live_test.app

detector:
	$(PYTHON) -m detector.app

workflow:
	$(PYTHON) -m workflow.app

test:
	$(PYTHON) -m pytest
