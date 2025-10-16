from __future__ import annotations

import logging
import sys

from PySide6.QtWidgets import QApplication

from .controller import WorkflowController
from .ui import WorkflowWindow


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s %(name)s: %(message)s")
    app = QApplication(sys.argv)
    window = WorkflowWindow()
    WorkflowController(window)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())

