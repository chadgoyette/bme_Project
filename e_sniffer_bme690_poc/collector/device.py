from __future__ import annotations

import logging
import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

LOGGER = logging.getLogger(__name__)


class BackendError(RuntimeError):
    """Raised when a hardware backend encounters an unrecoverable error."""


@dataclass
class SensorReading:
    gas_resistance_ohm: float
    temperature_C: float
    humidity_RH: float
    pressure_Pa: float
    heat_stable: bool
    status: Optional[int] = None

    def as_dict(self) -> Dict[str, float]:
        payload: Dict[str, float] = {
            "gas_resistance_ohm": float(self.gas_resistance_ohm),
            "sensor_temperature_C": float(self.temperature_C),
            "sensor_humidity_RH": float(self.humidity_RH),
            "pressure_Pa": float(self.pressure_Pa),
        }
        payload["heater_heat_stable"] = bool(self.heat_stable)
        if self.status is not None:
            payload["sensor_status_raw"] = int(self.status)
        return payload


class BackendBase:
    """Base class for sensor backends."""

    name = "base"

    def apply_and_read_step(self, temp_c: int, duration_ms: int) -> Optional[SensorReading]:
        """Apply heater settings and read the sensor in forced mode.

        Subclasses should return None if the reading failed (will be treated as NaN downstream).
        """
        raise NotImplementedError

    def close(self) -> None:  # pragma: no cover - no-op default
        pass


class BackendBME68xI2C(BackendBase):
    name = "bme68x_i2c"

    def __init__(self, address: int = 0x76) -> None:
        self.address = address
        try:
            from bme68x import BME68X  # type: ignore
        except Exception:  # pragma: no cover - driver optional
            BME68X = None  # noqa: N806
        self._driver_cls = BME68X
        if self._driver_cls is None:
            LOGGER.warning("bme68x driver not available; using synthetic readings.")
            self._sensor = None
        else:  # pragma: no cover - requires hardware
            self._sensor = self._driver_cls(i2c_addr=address)
            self._sensor.set_heater_profile_temperature([150], 150)
            self._sensor.set_filter_size(3)
            self._sensor.set_oversampling(
                hum=2, pres=4, temp=8
            )

    def apply_and_read_step(self, temp_c: int, duration_ms: int) -> Optional[SensorReading]:
        if self._sensor is None:
            # Synthetic fallback for development/testing.
            return self._synthetic_read(temp_c)

        try:  # pragma: no cover - requires hardware
            self._sensor.set_heater_profile_temperature([temp_c], duration_ms)
            self._sensor.set_heater_profile_duration([duration_ms])
            self._sensor.select_heater_profile(0)
            data = self._sensor.get_data()
            if not data:
                return None
            sample = data[0]
            heat_stable = bool(getattr(sample, "heat_stable", False))
            return SensorReading(
                gas_resistance_ohm=sample.gas_resistance,
                temperature_C=sample.temperature,
                humidity_RH=sample.humidity,
                pressure_Pa=sample.pressure,
                heat_stable=heat_stable,
                status=None,
            )
        except Exception as exc:
            LOGGER.error("BME68x read failed: %s", exc)
            return None

    def _synthetic_read(self, temp_c: int) -> SensorReading:
        # Very simple synthetic signal shaped by heater temp.
        base = 10_000 / max(temp_c, 1)
        timestamp = time.time()
        gas = base * (1.0 + 0.05 * (timestamp % 5))
        temp = 25.0 + (temp_c - 150) / 300.0
        humidity = 40.0 + ((temp_c - 180) / 220.0)
        pressure = 101_325.0 - (temp_c - 200) * 2.0
        return SensorReading(
            gas_resistance_ohm=gas,
            temperature_C=temp,
            humidity_RH=humidity,
            pressure_Pa=pressure,
            heat_stable=True,
            status=None,
        )


class BackendCOINES(BackendBase):
    name = "coines"

    ENV_EXECUTABLE = "BME69X_BRIDGE_EXE"

    def __init__(self, address: int = 0x76, exe_path: Optional[str | Path] = None) -> None:
        self.address = address
        self._proc: subprocess.Popen[str] | None = None
        self._exe_path = self._resolve_executable(exe_path)
        self._start_bridge()

    def apply_and_read_step(self, temp_c: int, duration_ms: int) -> Optional[SensorReading]:
        response = self._send_command(f"MEASURE {int(temp_c)} {int(duration_ms)}")
        if response.startswith("DATA "):
            parts = response.split()
            if len(parts) != 7:
                raise BackendError(f"Unexpected DATA payload from bridge: '{response}'")
            _, _timestamp, temp_str, pressure_str, humidity_str, gas_str, status_str = parts
            try:
                temperature = float(temp_str)
                pressure = float(pressure_str)
                humidity = float(humidity_str)
                gas = float(gas_str)
                status = int(status_str, 0)
            except ValueError as exc:  # pragma: no cover - validation
                raise BackendError(f"Unable to parse bridge response '{response}'") from exc

            required_bits = 0x80 | 0x20 | 0x10
            if (status & required_bits) != required_bits:
                LOGGER.warning("Bridge returned measurement with status 0x%02x", status)
                return None

            return SensorReading(
                gas_resistance_ohm=gas,
                temperature_C=temperature,
                humidity_RH=humidity,
                pressure_Pa=pressure,
                heat_stable=bool(status & 0x10),
                status=status,
            )

        if response.startswith("ERR "):
            LOGGER.warning("Bridge measurement error for temp=%s dur=%s -> %s", temp_c, duration_ms, response)
            return None

        if response.startswith("BYE"):
            raise BackendError("Bridge terminated unexpectedly during measurement.")

        LOGGER.warning("Unexpected bridge response: %s", response)
        return None

    def close(self) -> None:  # pragma: no cover - hardware interaction
        proc, self._proc = self._proc, None
        if proc is None:
            return

        try:
            if proc.stdin:
                proc.stdin.write("EXIT\n")
                proc.stdin.flush()
        except Exception:
            pass

        try:
            if proc.stdout:
                proc.stdout.readline()
        except Exception:
            pass

        try:
            proc.wait(timeout=1.0)
        except Exception:
            proc.kill()
        finally:
            if proc.stdin:
                proc.stdin.close()
            if proc.stdout:
                proc.stdout.close()

    def _start_bridge(self) -> None:
        try:
            self._proc = subprocess.Popen(
                [str(self._exe_path)],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                encoding="utf-8",
                bufsize=1,
            )
        except OSError as exc:  # pragma: no cover - runtime env
            raise BackendError(f"Failed to launch bridge executable '{self._exe_path}': {exc}") from exc

        while True:
            banner = self._readline()
            if banner == "READY":
                break
            if banner.startswith("ERR"):
                self.close()
                raise BackendError(f"Bridge initialization failed: '{banner}'")
            # Other informational banners (e.g., interface selection) are ignored.

    def _resolve_executable(self, override: Optional[str | Path]) -> Path:
        candidates = []
        if override:
            candidates.append(Path(override))

        env_override = os.environ.get(self.ENV_EXECUTABLE)
        if env_override:
            candidates.append(Path(env_override))

        base_dir = Path(__file__).resolve().parent
        candidates.extend(
            [
                base_dir / "native" / "bme69x_bridge" / "build" / "PC" / "bme69x_bridge_cli.exe",
                base_dir / "native" / "bme69x_bridge" / "bme69x_bridge_cli.exe",
            ]
        )

        for candidate in candidates:
            if candidate and candidate.exists():
                return candidate

        raise BackendError(
            "BME69x bridge executable not found. Build it via 'mingw32-make' in collector/native/bme69x_bridge "
            "or set BME69X_BRIDGE_EXE to the executable path."
        )

    def _readline(self) -> str:
        if not self._proc or not self._proc.stdout:
            raise BackendError("Bridge process is not running.")

        line = self._proc.stdout.readline()
        if not line:
            code = self._proc.poll()
            raise BackendError(f"Bridge process exited unexpectedly (code={code}).")

        return line.strip()

    def _send_command(self, command: str) -> str:
        if not self._proc or not self._proc.stdin:
            raise BackendError("Bridge process is not running.")

        try:
            self._proc.stdin.write(command + "\n")
            self._proc.stdin.flush()
        except Exception as exc:
            raise BackendError(f"Failed to send command to bridge: {exc}") from exc

        return self._readline()
