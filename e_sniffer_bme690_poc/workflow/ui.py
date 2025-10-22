from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Dict

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
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
        self._training_running = False
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

        self.combo_train_mode = QComboBox()
        self.combo_train_mode.addItems(["CNN (1D conv)", "Legacy (sklearn)"])
        self.combo_train_mode.currentIndexChanged.connect(self._update_training_mode_fields)

        self.label_data_source = QLabel("Prepared directory")
        self.edit_training_source = QLineEdit("")
        self.edit_training_source.textChanged.connect(self._update_training_button_state)
        self.btn_browse_training_source = QPushButton("Browse...")
        self.btn_browse_training_source.clicked.connect(self._browse_training_source)

        default_model_dir = Path("models").resolve()
        default_exp = default_model_dir / f"exp_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
        self.edit_train_out = QLineEdit(str(default_exp))
        self.btn_browse_train_out = QPushButton("Browse...")
        self.btn_browse_train_out.clicked.connect(self._browse_train_out)

        # Legacy fields
        self.label_model = QLabel("Model")
        self.combo_model = QComboBox()
        self.combo_model.addItems(["rf", "logreg", "gbt"])

        self.label_group = QLabel("Group column")
        self.edit_group = QLineEdit("specimen_id")

        self.label_cv = QLabel("CV folds")
        self.spin_cv = QSpinBox()
        self.spin_cv.setRange(2, 20)
        self.spin_cv.setValue(5)

        # Shared seed
        self.label_seed = QLabel("Random seed")
        self.spin_seed = QSpinBox()
        self.spin_seed.setRange(0, 1_000_000)
        self.spin_seed.setValue(42)

        # CNN fields
        self.label_epochs = QLabel("Epochs")
        self.spin_epochs = QSpinBox()
        self.spin_epochs.setRange(1, 500)
        self.spin_epochs.setValue(40)

        self.label_batch = QLabel("Batch size")
        self.spin_batch = QSpinBox()
        self.spin_batch.setRange(1, 512)
        self.spin_batch.setValue(32)

        self.label_lr = QLabel("Learning rate")
        self.double_lr = QDoubleSpinBox()
        self.double_lr.setDecimals(5)
        self.double_lr.setRange(1e-6, 1.0)
        self.double_lr.setSingleStep(0.0001)
        self.double_lr.setValue(0.001)

        self.label_val_fraction = QLabel("Val fraction")
        self.double_val_fraction = QDoubleSpinBox()
        self.double_val_fraction.setDecimals(2)
        self.double_val_fraction.setRange(0.05, 0.5)
        self.double_val_fraction.setSingleStep(0.05)
        self.double_val_fraction.setValue(0.2)

        self.label_patience = QLabel("Patience")
        self.spin_patience = QSpinBox()
        self.spin_patience.setRange(1, 50)
        self.spin_patience.setValue(5)

        self.btn_run_training = QPushButton("Run Training")
        self.btn_run_training.clicked.connect(self._emit_training)
        self.btn_run_training.setEnabled(False)
        self.label_training_status = QLabel("Status: waiting for data prep")

        training_layout.addWidget(QLabel("Training mode"), 0, 0)
        training_layout.addWidget(self.combo_train_mode, 0, 1)
        training_layout.addWidget(self.label_data_source, 1, 0)
        training_layout.addWidget(self.edit_training_source, 1, 1)
        training_layout.addWidget(self.btn_browse_training_source, 1, 2)
        training_layout.addWidget(QLabel("Output directory"), 2, 0)
        training_layout.addWidget(self.edit_train_out, 2, 1)
        training_layout.addWidget(self.btn_browse_train_out, 2, 2)

        training_layout.addWidget(self.label_model, 3, 0)
        training_layout.addWidget(self.combo_model, 3, 1)
        training_layout.addWidget(self.label_group, 4, 0)
        training_layout.addWidget(self.edit_group, 4, 1)
        training_layout.addWidget(self.label_cv, 5, 0)
        training_layout.addWidget(self.spin_cv, 5, 1)

        training_layout.addWidget(self.label_epochs, 6, 0)
        training_layout.addWidget(self.spin_epochs, 6, 1)
        training_layout.addWidget(self.label_batch, 7, 0)
        training_layout.addWidget(self.spin_batch, 7, 1)
        training_layout.addWidget(self.label_lr, 8, 0)
        training_layout.addWidget(self.double_lr, 8, 1)
        training_layout.addWidget(self.label_val_fraction, 9, 0)
        training_layout.addWidget(self.double_val_fraction, 9, 1)
        training_layout.addWidget(self.label_patience, 10, 0)
        training_layout.addWidget(self.spin_patience, 10, 1)

        training_layout.addWidget(self.label_seed, 11, 0)
        training_layout.addWidget(self.spin_seed, 11, 1)

        training_layout.addWidget(self.btn_run_training, 12, 0, 1, 1)
        training_layout.addWidget(self.label_training_status, 12, 1, 1, 2)

        layout.addWidget(training_group)

        self._legacy_widgets = [
            self.label_model,
            self.combo_model,
            self.label_group,
            self.edit_group,
            self.label_cv,
            self.spin_cv,
        ]
        self._cnn_widgets = [
            self.label_epochs,
            self.spin_epochs,
            self.label_batch,
            self.spin_batch,
            self.label_lr,
            self.double_lr,
            self.label_val_fraction,
            self.double_val_fraction,
            self.label_patience,
            self.spin_patience,
        ]
        self._update_training_mode_fields()

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

    def _browse_training_source(self) -> None:
        is_cnn = self.combo_train_mode.currentIndex() == 0
        current = self.edit_training_source.text()
        if is_cnn:
            path = QFileDialog.getExistingDirectory(self, "Select prepared directory", current or str(Path("prepared").resolve()))
            if path:
                self.edit_training_source.setText(path)
        else:
            path, _ = QFileDialog.getOpenFileName(
                self,
                "Select features.parquet",
                current or str(Path(".").resolve()),
                "Parquet (*.parquet)",
            )
            if path:
                self.edit_training_source.setText(path)

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
        mode = "cnn" if self.combo_train_mode.currentIndex() == 0 else "legacy"
        config: Dict[str, object] = {
            "mode": mode,
            "data_path": Path(self.edit_training_source.text()).expanduser(),
            "output_dir": Path(self.edit_train_out.text()).expanduser(),
            "seed": self.spin_seed.value(),
        }
        if mode == "legacy":
            config.update(
                {
                    "model": self.combo_model.currentText(),
                    "group_col": self.edit_group.text().strip(),
                    "cv_folds": self.spin_cv.value(),
                }
            )
        else:
            config.update(
                {
                    "epochs": self.spin_epochs.value(),
                    "batch_size": self.spin_batch.value(),
                    "learning_rate": self.double_lr.value(),
                    "val_fraction": self.double_val_fraction.value(),
                    "patience": self.spin_patience.value(),
                }
            )
        self.training_requested.emit(config)

    def _update_training_button_state(self) -> None:
        text = self.edit_training_source.text().strip()
        self.btn_run_training.setEnabled(bool(text) and not self._training_running)

    def _update_training_mode_fields(self) -> None:
        is_cnn = self.combo_train_mode.currentIndex() == 0
        self.label_data_source.setText("Prepared directory" if is_cnn else "Features parquet")
        placeholder = "Path to prepared/ dir" if is_cnn else "Path to features.parquet"
        self.edit_training_source.setPlaceholderText(placeholder)

        for widget in self._legacy_widgets:
            widget.setVisible(not is_cnn)
            if hasattr(widget, "setEnabled"):
                widget.setEnabled(not self._training_running and not is_cnn)

        for widget in self._cnn_widgets:
            widget.setVisible(is_cnn)
            if hasattr(widget, "setEnabled"):
                widget.setEnabled(not self._training_running and is_cnn)

        if not is_cnn:
            self.double_val_fraction.setValue(min(max(self.double_val_fraction.value(), 0.05), 0.5))

        self._update_training_button_state()

    # ------------------------------------------------------------------ Public helpers
    def set_dataprep_running(self, running: bool) -> None:
        self.btn_run_dataprep.setEnabled(not running)
        self.btn_browse_logs.setEnabled(not running)
        self.btn_browse_out.setEnabled(not running)
        self.spin_expected_steps.setEnabled(not running)
        self.check_drop_unstable.setEnabled(not running)

    def set_training_running(self, running: bool) -> None:
        self._training_running = running
        self.btn_run_training.setEnabled(not running and bool(self.edit_training_source.text().strip()))
        self.btn_browse_training_source.setEnabled(not running)
        self.btn_browse_train_out.setEnabled(not running)
        self.combo_train_mode.setEnabled(not running)
        self.spin_seed.setEnabled(not running)
        self._update_training_mode_fields()

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
        if sequences_path.exists():
            self.edit_training_source.setText(str(prepared_dir))
            models_root = Path("models").resolve()
            models_root.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            self.edit_train_out.setText(str(models_root / f"cnn_{timestamp}"))
            message = f"Status: tensors ready at {sequences_path}"
        else:
            message = "Status: data prep completed"
        self.set_training_status(message)
        self._update_training_button_state()
