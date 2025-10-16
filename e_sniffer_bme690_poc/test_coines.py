"""
Quick COINES sanity check for Application Board 3.1.
"""

from __future__ import annotations

import os
import sys

SDK_PATH = os.getenv("COINES_SDK_PATH", r"C:\COINES_SDK_main")
sys.path.insert(0, os.path.join(SDK_PATH, "coines-api", "pc", "python"))

import coinespy as cpy  # type: ignore  # noqa: E402


def main() -> None:
    print("COINES_SDK_PATH:", SDK_PATH)

    board = cpy.CoinesBoard()
    err = board.open_comm_interface(cpy.CommInterface.USB)
    print("open:", err)

    if err != cpy.ErrorCodes.COINES_SUCCESS:
        return

    try:
        print("set_vdd:", board.set_vdd(3.3))
        print("set_vddio:", board.set_vddio(3.3))
        bus = cpy.I2CBus.BUS_I2C_0
        err = board.config_i2c_bus(bus, 0x76, cpy.I2CMode.FAST_MODE)
        print("config:", err)
        if err == cpy.ErrorCodes.COINES_SUCCESS:
            chip = board.read_i2c(bus, 0xD0, 1, sensor_interface_detail=0x76)
            print("chip id:", chip)
    finally:
        board.close_comm_interface()


if __name__ == "__main__":
    main()
