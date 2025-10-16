# Track B Logger Skeleton

This directory contains a stub for a COINES-based BME690 logger CLI. The goal is to provide a starting point that accepts the intended command line arguments and writes a Bosch Development Desktop compatible CSV header. Hardware integration calls are marked with `TODO` comments.

## Building

```bash
cmake -S track_b/logger -B track_b/logger/build
cmake --build track_b/logger/build
```

## Usage

```
bme690_logger --port auto --sample-rate 2 --heater-profile fixed:320C --duration-sec 1800 --warmup-sec 600 --out raw.csv
bme690_logger --port auto --sample-rate 2 --heater-profile steps:250C:60,300C:60,350C:60 --cycles 10 --out raw.csv
```

Currently the binary only parses the options and writes a CSV header to `--out`. Integrate COINES initialisation and data acquisition where indicated in `src/main.c`.
