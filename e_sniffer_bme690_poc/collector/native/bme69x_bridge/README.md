# BME69x Bridge CLI

Helper executable that wraps the Bosch Sensortec BME69x SensorAPI forced-mode
flow so the Python collector can request heater steps one at a time.

## Prerequisites

- COINES SDK cloned to `C:\COINES_SDK_main` (override with `COINES_INSTALL_PATH`)
- MinGW toolchain on `PATH` (`mingw32-make`, `gcc`, etc.)
- Git Bash or another shell that provides `rm` for the COINES makefiles

## Build

From within this directory run:

```powershell
$env:PATH='C:\Program Files\Git\usr\bin;C:\Users\chadg\toolchains\winlibs\mingw64\bin;' + $env:PATH
mingw32-make
```

The executable `bme69x_bridge_cli.exe` will be emitted to `build/PC/`.

## Usage

Run the executable and communicate over stdin/stdout:

```
bme69x_bridge_cli.exe
READY
MEASURE 320 150
DATA 3553595575 24.90 101722.34 49.11 16293.28 0xb0
EXIT
BYE
```

Commands:

- `MEASURE <temp_C> <duration_ms>` – perform one forced-mode measurement
- `PING` – health check (`PONG`)
- `EXIT` – shut down the bridge (`BYE`)
