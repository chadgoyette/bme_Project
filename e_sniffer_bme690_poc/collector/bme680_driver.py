# MIT License
# Copied and adapted from the official bme680 Python package
# Source: https://github.com/pimoroni/bme680-python (MIT)

from __future__ import annotations

import math
import time
from dataclasses import dataclass


# Constants replicated from the original library
I2C_ADDR_PRIMARY = 0x76
I2C_ADDR_SECONDARY = 0x77

CHIP_ID = 0x61
CHIP_ID_ADDR = 0xD0
CHIP_VARIANT_ADDR = 0xF0

COEFF_ADDR1 = 0x89
COEFF_ADDR1_LEN = 25
COEFF_ADDR2 = 0xE1
COEFF_ADDR2_LEN = 16
FIELD0_ADDR = 0x1D
FIELD_LENGTH = 17
SOFT_RESET_ADDR = 0xE0
SOFT_RESET_CMD = 0xB6
CONF_HEAT_CTRL_ADDR = 0x70
CONF_ODR_RUN_GAS_NBC_ADDR = 0x71
CONF_OS_H_ADDR = 0x72
MEM_PAGE_ADDR = 0x73
CONF_T_P_MODE_ADDR = 0x74
GAS_WAIT0_ADDR = 0x64
RES_HEAT0_ADDR = 0x5A

RESET_PERIOD = 10
POLL_PERIOD_MS = 10

ENABLE_GAS_MEAS = 0x01
DISABLE_GAS_MEAS = 0x00

ENABLE_HEATER = 0x00
DISABLE_HEATER = 0x08

GAS_MEAS_MSK = 0x30
RUN_GAS_ENABLE = 0x10
RUN_GAS_DISABLE = 0x00
NB_CONV_MIN = 0
NB_CONV_MAX = 9

FILTER_SIZE_0 = 0
FILTER_SIZE_1 = 1
FILTER_SIZE_3 = 2
FILTER_SIZE_7 = 3
FILTER_SIZE_15 = 4
FILTER_SIZE_31 = 5
FILTER_SIZE_63 = 6
FILTER_SIZE_127 = 7

OS_NONE = 0
OS_1X = 1
OS_2X = 2
OS_4X = 3
OS_8X = 4
OS_16X = 5

SLEEP_MODE = 0
FORCED_MODE = 1

REG_BUFFER_LENGTH = 0x41
BME680_REG_HUM_LSB = 0x25

lookupTable1 = [
    2147483647, 2147483647, 2147483647, 2147483647,
    2147483647, 2126008810, 2147483647, 2130303777,
    2147483647, 2147483647, 2143188679, 2136746228,
    2147483647, 2126008810, 2147483647, 2147483647,
]

lookupTable2 = [
    4096000000, 2048000000, 1024000000, 512000000,
    255744255, 127110228, 64000000, 32258064,
    16016016, 8000000, 4000000, 2000000,
    1000000, 500000, 250000, 125000,
]


def _twos_comp(val: int, bits: int) -> int:
    """Compute the 2's complement of int value val."""
    if val & (1 << (bits - 1)):
        val = val - (1 << bits)
    return val


def _bytes_to_word(msb: int, lsb: int) -> int:
    return (msb << 8) | lsb


@dataclass
class CalibrationData:
    par_t1: int = 0
    par_t2: int = 0
    par_t3: int = 0
    par_p1: int = 0
    par_p2: int = 0
    par_p3: int = 0
    par_p4: int = 0
    par_p5: int = 0
    par_p6: int = 0
    par_p7: int = 0
    par_p8: int = 0
    par_p9: int = 0
    par_p10: int = 0
    par_h1: int = 0
    par_h2: int = 0
    par_h3: int = 0
    par_h4: int = 0
    par_h5: int = 0
    par_h6: int = 0
    par_h7: int = 0
    par_gh1: int = 0
    par_gh2: int = 0
    par_gh3: int = 0
    res_heat_val: int = 0
    res_heat_range: int = 0
    range_sw_err: int = 0
    t_fine: int = 0

    def set_from_array(self, coeff: list[int]) -> None:
        self.par_t1 = _bytes_to_word(coeff[34], coeff[33])
        self.par_t2 = _bytes_to_word(coeff[2], coeff[1])
        self.par_t3 = coeff[3]
        self.par_p1 = (_bytes_to_word(coeff[6], coeff[5]))
        self.par_p2 = _twos_comp(_bytes_to_word(coeff[8], coeff[7]), 16)
        self.par_p3 = coeff[9]
        self.par_p4 = _twos_comp(_bytes_to_word(coeff[12], coeff[11]), 16)
        self.par_p5 = _twos_comp(_bytes_to_word(coeff[14], coeff[13]), 16)
        self.par_p6 = coeff[16]
        self.par_p7 = coeff[15]
        self.par_p8 = _twos_comp(_bytes_to_word(coeff[20], coeff[19]), 16)
        self.par_p9 = _twos_comp(_bytes_to_word(coeff[22], coeff[21]), 16)
        self.par_p10 = coeff[23]
        self.par_h1 = _bytes_to_word(coeff[27], coeff[26]) >> 4
        self.par_h2 = _bytes_to_word(coeff[25], coeff[24]) >> 4
        self.par_h3 = coeff[28]
        self.par_h4 = coeff[29]
        self.par_h5 = coeff[30]
        self.par_h6 = coeff[31]
        self.par_h7 = coeff[32]
        self.par_gh1 = coeff[36]
        self.par_gh2 = _twos_comp(_bytes_to_word(coeff[35], coeff[34]), 16)
        self.par_gh3 = coeff[37]

    def set_other(self, heat_range: list[int], heat_value: int, sw_err: int) -> None:
        self.res_heat_range = (heat_range[0] & 0x30) >> 4
        self.res_heat_val = heat_value
        self.range_sw_err = (sw_err & 0xF0) >> 4


@dataclass
class FieldData:
    temperature: float = 0.0
    pressure: float = 0.0
    humidity: float = 0.0
    gas_resistance: float = 0.0
    status: int = 0
    gas_index: int = 0
    meas_index: int = 0
    heat_stable: bool = False


class BME680Data:
    def __init__(self) -> None:
        self.calibration_data = CalibrationData()
        self.data = FieldData()
        self.tph_settings = TPHSettings()
        self.gas_settings = GasSettings()
        self.ambient_temperature = 2500  # hundredths of degree
        self.power_mode = SLEEP_MODE


@dataclass
class TPHSettings:
    os_hum: int = OS_NONE
    os_pres: int = OS_NONE
    os_temp: int = OS_NONE
    filter: int = FILTER_SIZE_0


@dataclass
class GasSettings:
    nb_conv: int = 0
    heater_temp: int = 0
    heater_dur: int = 0
    run_gas: int = ENABLE_GAS_MEAS


class BME680(BME680Data):
    def __init__(self, i2c_addr: int = I2C_ADDR_PRIMARY, i2c_device=None) -> None:
        super().__init__()
        self.i2c_addr = i2c_addr
        if i2c_device is None:
            raise RuntimeError("An I2C device instance must be supplied.")
        self._i2c = i2c_device
        self.chip_id = self._get_regs(CHIP_ID_ADDR, 1)[0]
        if self.chip_id != CHIP_ID:
            raise RuntimeError(f"BME68x not found. Got chip ID 0x{self.chip_id:02x}")
        self.variant = self._get_regs(CHIP_VARIANT_ADDR, 1)[0]
        self.soft_reset()
        self.set_power_mode(SLEEP_MODE)
        self._get_calibration_data()
        self.set_humidity_oversample(OS_2X)
        self.set_pressure_oversample(OS_4X)
        self.set_temperature_oversample(OS_8X)
        self.set_filter(FILTER_SIZE_3)
        self.set_gas_status(ENABLE_GAS_MEAS)
        self.get_sensor_data()

    # Low-level register helpers ------------------------------------------------

    def _get_regs(self, register: int, length: int) -> list[int]:
        if length == 1:
            return [self._i2c.read_byte_data(self.i2c_addr, register)]
        return self._i2c.read_i2c_block_data(self.i2c_addr, register, length)

    def _set_regs(self, register: int, value) -> None:
        if isinstance(value, int):
            self._i2c.write_byte_data(self.i2c_addr, register, value)
        else:
            self._i2c.write_i2c_block_data(self.i2c_addr, register, value)

    # Device setup -------------------------------------------------------------

    def soft_reset(self) -> None:
        self._set_regs(SOFT_RESET_ADDR, SOFT_RESET_CMD)
        time.sleep(RESET_PERIOD / 1000.0)

    def set_power_mode(self, mode: int) -> None:
        current = self._get_regs(CONF_T_P_MODE_ADDR, 1)[0]
        current &= ~0x03
        current |= mode
        self._set_regs(CONF_T_P_MODE_ADDR, current)
        self.power_mode = mode

    def set_humidity_oversample(self, value: int) -> None:
        self.tph_settings.os_hum = value
        self._set_regs(CONF_OS_H_ADDR, value)

    def set_pressure_oversample(self, value: int) -> None:
        current = self._get_regs(CONF_T_P_MODE_ADDR, 1)[0]
        current = current & ~(0x1C)
        current |= (value << 2)
        self._set_regs(CONF_T_P_MODE_ADDR, current)
        self.tph_settings.os_pres = value

    def set_temperature_oversample(self, value: int) -> None:
        current = self._get_regs(CONF_T_P_MODE_ADDR, 1)[0]
        current = current & ~(0xE0)
        current |= (value << 5)
        self._set_regs(CONF_T_P_MODE_ADDR, current)
        self.tph_settings.os_temp = value

    def set_filter(self, value: int) -> None:
        current = self._get_regs(CONF_ODR_RUN_GAS_NBC_ADDR, 1)[0]
        current = current & ~(0x1C)
        current |= (value << 2)
        self._set_regs(CONF_ODR_RUN_GAS_NBC_ADDR, current)
        self.tph_settings.filter = value

    def set_gas_status(self, value: int) -> None:
        current = self._get_regs(CONF_ODR_RUN_GAS_NBC_ADDR, 1)[0]
        current = current & ~(0x10)
        current |= (value << 4)
        self._set_regs(CONF_ODR_RUN_GAS_NBC_ADDR, current)
        self.gas_settings.run_gas = value

    def select_gas_heater_profile(self, profile: int) -> None:
        if profile < 0 or profile > 9:
            raise ValueError("Heater profile must be 0–9")
        current = self._get_regs(CONF_ODR_RUN_GAS_NBC_ADDR, 1)[0]
        current = current & ~(0x0F)
        current |= profile
        self._set_regs(CONF_ODR_RUN_GAS_NBC_ADDR, current)
        self.gas_settings.nb_conv = profile

    def set_gas_heater_temperature(self, temperature: int, nb_profile: int = 0) -> None:
        temp = int(self._calc_heater_resistance(temperature))
        self._set_regs(RES_HEAT0_ADDR + nb_profile, temp)
        self.gas_settings.heater_temp = temperature

    def set_gas_heater_duration(self, duration: int, nb_profile: int = 0) -> None:
        self._set_regs(GAS_WAIT0_ADDR + nb_profile, self._calc_heater_duration(duration))
        self.gas_settings.heater_dur = duration

    # Calibration ----------------------------------------------------------------

    def _get_calibration_data(self) -> None:
        coeff = self._get_regs(COEFF_ADDR1, COEFF_ADDR1_LEN)
        coeff += self._get_regs(COEFF_ADDR2, COEFF_ADDR2_LEN)
        heat_range = self._get_regs(0x02, 1)
        heat_value = _twos_comp(self._get_regs(0x00, 1)[0], 8)
        sw_err = _twos_comp(self._get_regs(0x04, 1)[0], 8)
        self.calibration_data.set_from_array(coeff)
        self.calibration_data.set_other(heat_range, heat_value, sw_err)

    # Reading --------------------------------------------------------------------

    def get_sensor_data(self) -> bool:
        self.set_power_mode(FORCED_MODE)
        for _ in range(10):
            status = self._get_regs(FIELD0_ADDR, 1)[0]
            if status & 0x80 == 0:
                time.sleep(POLL_PERIOD_MS / 1000.0)
                continue
            regs = self._get_regs(FIELD0_ADDR, FIELD_LENGTH)
            self.data.status = regs[0] & 0x80
            self.data.gas_index = regs[0] & 0x0F
            self.data.meas_index = regs[1]
            adc_pres = (regs[2] << 12) | (regs[3] << 4) | (regs[4] >> 4)
            adc_temp = (regs[5] << 12) | (regs[6] << 4) | (regs[7] >> 4)
            adc_hum = (regs[8] << 8) | regs[9]
            adc_gas_res = (regs[13] << 2) | (regs[14] >> 6)
            gas_range = regs[14] & 0x0F

            temperature = self._calc_temperature(adc_temp)
            self.data.temperature = temperature / 100.0
            self.ambient_temperature = temperature
            self.data.pressure = self._calc_pressure(adc_pres) / 100.0
            self.data.humidity = self._calc_humidity(adc_hum) / 1000.0
            self.data.gas_resistance = self._calc_gas_resistance_low(adc_gas_res, gas_range)
            self.data.heat_stable = True
            return True
        return False

    # Compensation algorithms ----------------------------------------------------

    def _calc_temperature(self, temp_adc: int) -> int:
        cal = self.calibration_data
        var1 = (temp_adc >> 3) - (cal.par_t1 << 1)
        var2 = (var1 * cal.par_t2) >> 11
        var3 = ((var1 >> 1) * (var1 >> 1)) >> 12
        var3 = (var3 * (cal.par_t3 << 4)) >> 14
        cal.t_fine = int(var2 + var3)
        return ((cal.t_fine * 5) + 128) >> 8

    def _calc_pressure(self, press_adc: int) -> int:
        cal = self.calibration_data
        var1 = cal.t_fine >> 1
        var1 -= 64000
        var2 = (((var1 >> 2) * (var1 >> 2)) >> 11) * cal.par_p6
        var2 = var2 >> 2
        var2 += (var1 * cal.par_p5) << 1
        var2 = (var2 >> 2) + (cal.par_p4 << 16)
        var1 = (((cal.par_p3 * ((var1 >> 2) * (var1 >> 2)) >> 13) >> 3) + ((cal.par_p2 * var1) >> 1)) >> 18
        var1 = ((32768 + var1) * cal.par_p1) >> 15
        if var1 == 0:
            return 0
        pressure = ((1048576 - press_adc) - (var2 >> 12)) * 3125
        if pressure >= (1 << 31):
            pressure = (pressure // var1) << 1
        else:
            pressure = (pressure << 1) // var1
        var1 = (cal.par_p9 * ((pressure >> 3) * (pressure >> 3) >> 13)) >> 12
        var2 = ((pressure >> 2) * cal.par_p8) >> 13
        var3 = ((pressure >> 8) * (pressure >> 8) * (pressure >> 8) * cal.par_p10) >> 17
        pressure = pressure + ((var1 + var2 + var3 + (cal.par_p7 << 7)) >> 4)
        return pressure

    def _calc_humidity(self, hum_adc: int) -> int:
        cal = self.calibration_data
        temp_scaled = ((cal.t_fine * 5) + 128) >> 8
        var1 = (hum_adc - (cal.par_h1 * 16)) - (((temp_scaled * cal.par_h3) // 100) >> 1)
        var2 = (
            cal.par_h2
            * (
                ((temp_scaled * cal.par_h4) // 100)
                + (((temp_scaled * ((temp_scaled * cal.par_h5) // 100)) >> 6) // 100)
                + (1 << 14)
            )
        ) >> 10
        var3 = var1 * var2
        var4 = cal.par_h6 << 7
        var4 = (var4 + ((temp_scaled * cal.par_h7) // 100)) >> 4
        var5 = ((var3 >> 14) * (var3 >> 14)) >> 10
        var6 = (var4 * var5) >> 1
        calc_hum = (((var3 + var6) >> 10) * 1000) >> 12
        return min(max(calc_hum, 0), 100000)

    def _calc_gas_resistance_low(self, gas_res_adc: int, gas_range: int) -> float:
        cal = self.calibration_data
        var1 = (1340 + (5 * cal.range_sw_err)) * lookupTable1[gas_range]
        var1 >>= 10
        var2 = ((gas_res_adc << 15) - 16777216) + var1
        if var2 == 0:
            return 0.0
        gas_res = (lookupTable2[gas_range] * var1) >> 9
        gas_res = (gas_res / var2) * 100.0
        return gas_res

    def _calc_heater_resistance(self, temperature: int) -> float:
        cal = self.calibration_data
        temperature = max(200, min(400, temperature))
        var1 = ((cal.ambient_temperature * cal.par_gh3) / 1000) * 256
        var2 = (cal.par_gh1 + 784) * (((((cal.par_gh2 + 154009) * temperature * 5) / 100) + 3276800) / 10)
        var3 = var1 + (var2 / 2)
        var4 = var3 / (cal.res_heat_range + 4)
        var5 = (131 * cal.res_heat_val) + 65536
        heatr_res_x100 = (((var4 / var5) - 250) * 34)
        return (heatr_res_x100 + 50) / 100

    @staticmethod
    def _calc_heater_duration(duration: int) -> int:
        if duration < 0xFC0:
            factor = 0
            while duration > 0x3F:
                duration = duration >> 2
                factor += 1
            return int(duration + (factor << 6))
        return 0xFF
