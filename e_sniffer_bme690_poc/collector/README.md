# Collect Application (Heater Profiles)

The upgraded collector application drives a Bosch BME690 in forced mode with heater profiles, records metadata, and logs live sensor readings to CSV. Profiles can be created, edited, imported, and exported directly from the UI.

## Handy Commands (PowerShell)

```powershell
cd C:\Users\chadg\OneDrive\BME_Sensor_Trainer\e_sniffer_bme690_poc
.\.venv\Scripts\Activate
python -m collector.collect
```

> Tip: run `deactivate` when you're done to leave the virtual environment.

## Key Features

- Heater profile manager with editable step tables (temperature/duration), validation, and `.bmeprofile` import/export.
- Two built-in read-only templates: **Broad Sweep (meat)** and **VOC/IAQ**.
- Run pane captures metadata, lets you choose capture cycles & warmup skips, and shows live status readouts.
- Per-run output folder picker so each specimen can be logged to its own directory (date-stamped subfolders are created automatically).
- Heater durations are configured in ticks (1 tick = 140 ms) for extended dwell times.
- The collector discards the first sample after each heater change and only logs data once the firmware reports heater stability.
- CSV logging with provenance (`profile_hash`) and a deterministic header layout.
- Headless CLI for automation: `python -m collector.collect --headless ...`.
- Optional COINES backend for Application Board 3.0 + BME68x shuttle (auto-connects when SDK is installed).

## Running the GUI

```bash
python -m collector.collect
```

The window opens with the last-used profile (or the default broad sweep). Use the **Profiles** pane to create/duplicate profiles, edit steps, and export them. In the run panel pick the capture count (cycles), warm-up skips, and choose an output folder for the CSV (handy for specimen-specific directories), then press **Start** to warm up the sensor and begin logging. Press **Stop** (or `Ctrl+R`) to end the run gracefully.

CSV files are stored under:

```
<output folder>/<UTC date>/bme690_<sample>_<timestamp>.csv
```

Each row includes heater command, sensor readings, metadata, backend identifier, and SHA1 hash of the profile for traceability.
### Recommended Sampling Routine

1. Load the meat sample into your headspace fixture and allow 2–3 minutes for the headspace to equilibrate (mirroring the dwell used in [Li & Suslick, 2016](https://doi.org/10.1021/acssensors.6b00492)).
2. Start the collector with a profile such as `AGING-BEEF-6`. The application automatically runs cycles back-to-back to capture both steady-state and kinetic behaviour.
3. Leave the default "Skip first cycles" value (3) so humidity and thermal transients are discarded. Adjust if your setup needs more warmup—similar discard phases are reported for IoT e-nose monitoring [Pham et al., 2024](https://doi.org/10.51316/jst.173.etsd.2024.34.2.5).
4. Capture the desired number of production cycles (typically 10–20). The UI and CSV only log those capture cycles; warmup cycles stay off-disk.
5. During each heater step the collector throws away the first measurement and only records data once the firmware reports `heat_stab=1`, supporting reproducible kinetics as highlighted by [Kodogiannis & Alshejari, 2025](https://doi.org/10.3390/s25103198).


### Using COINES (Application Board 3.x)

The collector now mirrors the proven Bosch SensorAPI flow via a native helper (`collector/native/bme69x_bridge`).

1. Install the COINES SDK (v2.11 or newer) to `C:\COINES_SDK_main` (override with `COINES_INSTALL_PATH` if needed).
2. Install or unpack a MinGW toolchain (for example the winlibs bundle) and ensure `mingw32-make`, `gcc`, and Git's `rm` utility are on `PATH`.
3. Build the bridge executable:
   ```powershell
   cd collector\native\bme69x_bridge
   $env:PATH='C:\Program Files\Git\usr\bin;C:\Users\chadg\toolchains\winlibs\mingw64\bin;' + $env:PATH
   mingw32-make
   ```
   This writes `bme69x_bridge_cli.exe` next to the Makefile. Set `BME69X_BRIDGE_EXE` if you move it elsewhere.
4. Connect the Application Board 3.x (bridge firmware) with the BME690 shuttle. The helper powers the board and uses SPI automatically.
5. In the collector UI (or headless mode) choose a profile whose backend is `coines` and start the run. The backend streams heater steps to the helper and ingests the resulting `DATA` lines in real time.

If the bridge prints `ERR INIT ...`, confirm the board is in bridge mode, the USB driver is installed, and no other program has the USB interface open.

## Headless Mode

```bash
python -m collector.collect \
  --headless \
  --profile path/to/profile.bmeprofile \
  --cycles 15 \
  --skip-cycles 3 \
  --meta '{"sample_name":"steakA","specimen_id":"S001","storage":"refrigerated","notes":"day1"}'
```

Headless mode mirrors the GUI run-loop: it skips the configured warmup cycles, records the requested capture cycles, then exits once the cycle quota is reached.


## References

- Z. Li and K. S. Suslick, "Portable Optoelectronic Nose for Monitoring Meat Freshness," *ACS Sensors*, 2016, 1(11), 1330–1335. https://doi.org/10.1021/acssensors.6b00492
- H. T. Pham et al., "An IoT-Based Smart Electronic Nose System for Non-Destructive Meat Freshness Monitoring," *JST: Engineering and Technology for Sustainable Development*, 2024, 34(2), 31–39. https://doi.org/10.51316/jst.173.etsd.2024.34.2.5
- V. S. Kodogiannis and A. Alshejari, "Data Fusion of Electronic Nose and Multispectral Imaging for Meat Spoilage Detection Using Machine Learning Techniques," *Sensors*, 2025, 25(10), 3198. https://doi.org/10.3390/s25103198
