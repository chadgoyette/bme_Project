from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Dict

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)


class WorkflowWindow(QMainWindow):
    dataprep_requested = Signal(dict)
    training_requested = Signal(dict)

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("E-Sniffer Workflow")

        self._log_buffer = ""
        self._build_ui()
        self._update_training_button_state()

    # ------------------------------------------------------------------ UI setup
    def _build_ui(self) -> None:
        central = QWidget(self)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        dataprep_group = QGroupBox("Data Preparation")
        dataprep_layout = QGridLayout(dataprep_group)
        dataprep_layout.setHorizontalSpacing(10)
        dataprep_layout.setVerticalSpacing(6)

        self.edit_logs_root = QLineEdit(str(Path("logs").resolve()))
        self.btn_browse_logs = QPushButton("Browse...")
        self.btn_browse_logs.clicked.connect(self._browse_logs_root)

        self.edit_prep_out = QLineEdit(str(Path("prepared").resolve()))
        self.btn_browse_out = QPushButton("Browse...")
        self.btn_browse_out.clicked.connect(self._browse_prep_out)

        self.spin_expected_steps = QSpinBox()
        self.spin_expected_steps.setRange(0, 1000)
        self.spin_expected_steps.setValue(0)
        self.spin_expected_steps.setToolTip("Set to 0 to infer the step count from the first valid cycle.")

        self.check_drop_unstable = QCheckBox("Drop heater_unstable rows")
        self.check_drop_unstable.setChecked(True)

        self.btn_run_dataprep = QPushButton("Run Data Prep")
        self.btn_run_dataprep.clicked.connect(self._emit_dataprep)
        self.label_dataprep_status = QLabel("Status: idle")

        dataprep_layout.addWidget(QLabel("Logs root"), 0, 0)
        dataprep_layout.addWidget(self.edit_logs_root, 0, 1)
        dataprep_layout.addWidget(self.btn_browse_logs, 0, 2)
        dataprep_layout.addWidget(QLabel("Output directory"), 1, 0)
        dataprep_layout.addWidget(self.edit_prep_out, 1, 1)
        dataprep_layout.addWidget(self.btn_browse_out, 1, 2)

        dataprep_layout.addWidget(QLabel("Expected steps (0 = infer)"), 2, 0)
        dataprep_layout.addWidget(self.spin_expected_steps, 2, 1)
        dataprep_layout.addWidget(self.check_drop_unstable, 3, 0, 1, 3)

        dataprep_layout.addWidget(self.btn_run_dataprep, 4, 0, 1, 1)
        dataprep_layout.addWidget(self.label_dataprep_status, 4, 1, 1, 2)

        layout.addWidget(dataprep_group)

        training_group = QGroupBox("Training")
        training_layout = QGridLayout(training_group)
        training_layout.setHorizontalSpacing(10)
        training_layout.setVerticalSpacing(6)

        self.edit_features = QLineEdit("")
        self.edit_features.textChanged.connect(self._update_training_button_state)
        self.btn_browse_features = QPushButton("Browse...")
        self.btn_browse_features.clicked.connect(self._browse_features)

        default_model_dir = Path("models").resolve()
        default_exp = default_model_dir / f"exp_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
        self.edit_train_out = QLineEdit(str(default_exp))
        self.btn_browse_train_out = QPushButton("Browse...")
        self.btn_browse_train_out.clicked.connect(self._browse_train_out)

        self.combo_model = QComboBox()
        self.combo_model.addItems(["rf", "logreg", "gbt"])

        self.edit_group = QLineEdit("specimen_id")

        self.spin_cv = QSpinBox()
        self.spin_cv.setRange(2, 20)
        self.spin_cv.setValue(5)

        self.spin_seed = QSpinBox()
        self.spin_seed.setRange(0, 1_000_000)
        self.spin_seed.setValue(42)

        self.btn_run_training = QPushButton("Run Training")
        self.btn_run_training.clicked.connect(self._emit_training)
        self.btn_run_training.setEnabled(False)
        self.label_training_status = QLabel("Status: waiting for data prep")

        training_layout.addWidget(QLabel("Features parquet"), 0, 0)
        training_layout.addWidget(self.edit_features, 0, 1)
        training_layout.addWidget(self.btn_browse_features, 0, 2)
        training_layout.addWidget(QLabel("Output directory"), 1, 0)
        training_layout.addWidget(self.edit_train_out, 1, 1)
        training_layout.addWidget(self.btn_browse_train_out, 1, 2)

        training_layout.addWidget(QLabel("Model"), 2, 0)
        training_layout.addWidget(self.combo_model, 2, 1)
        training_layout.addWidget(QLabel("Group column"), 3, 0)
        training_layout.addWidget(self.edit_group, 3, 1)
        training_layout.addWidget(QLabel("CV folds"), 4, 0)
        training_layout.addWidget(self.spin_cv, 4, 1)
        training_layout.addWidget(QLabel("Random seed"), 5, 0)
        training_layout.addWidget(self.spin_seed, 5, 1)

        training_layout.addWidget(self.btn_run_training, 6, 0, 1, 1)
        training_layout.addWidget(self.label_training_status, 6, 1, 1, 2)

        layout.addWidget(training_group)

        log_group = QGroupBox("Pipeline Log")
        log_layout = QVBoxLayout(log_group)
        self.log_output = QPlainTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setLineWrapMode(QPlainTextEdit.NoWrap)
        log_layout.addWidget(self.log_output)

        layout.addWidget(log_group, stretch=1)
        layout.addStretch()

        self.setCentralWidget(central)

    # ------------------------------------------------------------------ Event helpers
    def _browse_logs_root(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Select logs root", self.edit_logs_root.text())
        if path:
            self.edit_logs_root.setText(path)

    def _browse_prep_out(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Select output directory", self.edit_prep_out.text())
        if path:
            self.edit_prep_out.setText(path)

    def _browse_features(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select prepared data",
            filter="Prepared (*.npz *.parquet);;All files (*)",
        )
        if path:
            self.edit_features.setText(path)

    def _browse_train_out(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Select training output directory", self.edit_train_out.text())
        if path:
            self.edit_train_out.setText(path)

    def _emit_dataprep(self) -> None:
        config: Dict[str, object] = {
            "logs_root": Path(self.edit_logs_root.text()).expanduser(),
            "out_dir": Path(self.edit_prep_out.text()).expanduser(),
            "expected_steps": self.spin_expected_steps.value(),
            "drop_unstable": self.check_drop_unstable.isChecked(),
        }
        self.dataprep_requested.emit(config)

    def _emit_training(self) -> None:
        config: Dict[str, object] = {
            "features_path": Path(self.edit_features.text()).expanduser(),
            "output_dir": Path(self.edit_train_out.text()).expanduser(),
            "model": self.combo_model.currentText(),
            "group_col": self.edit_group.text().strip(),
            "cv_folds": self.spin_cv.value(),
            "seed": self.spin_seed.value(),
        }
        self.training_requested.emit(config)

    def _update_training_button_state(self) -> None:
        text = self.edit_features.text().strip()
        self.btn_run_training.setEnabled(bool(text))

    # ------------------------------------------------------------------ Public helpers
    def set_dataprep_running(self, running: bool) -> None:
        self.btn_run_dataprep.setEnabled(not running)
        self.btn_browse_logs.setEnabled(not running)
        self.btn_browse_out.setEnabled(not running)
        self.spin_expected_steps.setEnabled(not running)
        self.check_drop_unstable.setEnabled(not running)

    def set_training_running(self, running: bool) -> None:
        self.btn_run_training.setEnabled(not running and bool(self.edit_features.text().strip()))
        self.btn_browse_features.setEnabled(not running)
        self.btn_browse_train_out.setEnabled(not running)
        self.combo_model.setEnabled(not running)
        self.edit_group.setEnabled(not running)
        self.spin_cv.setEnabled(not running)
        self.spin_seed.setEnabled(not running)

    def set_dataprep_status(self, text: str) -> None:
        self.label_dataprep_status.setText(text)

    def set_training_status(self, text: str) -> None:
        self.label_training_status.setText(text)

    def append_log(self, text: str) -> None:
        if not text:
            return
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        self._log_buffer += text
        lines = self._log_buffer.split("\n")
        self._log_buffer = lines[-1]
        for line in lines[:-1]:
            self.log_output.appendPlainText(line)

    def clear_log(self) -> None:
        self.log_output.clear()
        self._log_buffer = ""

    def flush_log(self) -> None:
        if self._log_buffer:
            self.log_output.appendPlainText(self._log_buffer)
            self._log_buffer = ""

    def show_error(self, message: str) -> None:
        QMessageBox.critical(self, "Workflow error", message, QMessageBox.StandardButton.Ok)

    def notify_dataprep_complete(self, prepared_dir: Path) -> None:
        sequences_path = prepared_dir / "sequences.npz"
        summary_path = prepared_dir / "summary.json"
        message = f"Status: tensors ready at {sequences_path}" if sequences_path.exists() else "Status: data prep completed"
        self.set_training_status(message)
        self._update_training_button_state()
