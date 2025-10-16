from __future__ import annotations

import logging
import sys

from PySide6.QtWidgets import QApplication

from .controller import DetectorController
from .ui import DetectorWindow


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s %(name)s: %(message)s")
    app = QApplication(sys.argv)
    window = DetectorWindow()
    DetectorController(window)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())

