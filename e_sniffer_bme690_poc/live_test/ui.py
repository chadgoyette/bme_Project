from __future__ import annotations

from typing import Dict, List, Optional, Tuple

import pandas as pd
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QDoubleSpinBox,
    QGridLayout,
    QGroupBox,
    QLabel,
    QMainWindow,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)


class LiveTestWindow(QMainWindow):
    csv_selected = Signal(str)
    metadata_selected = Signal(str)
    model_selected = Signal(str)
    mode_changed = Signal(str)
    start_requested = Signal()
    stop_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("E-Sniffer Detector")

        self._class_widgets: Dict[str, Tuple[QLabel, QLabel]] = {}
        self._led_styles = {
            "off": "background-color: #6c6c6c; border-radius: 7px;",
            "on": "background-color: #2ecc71; border-radius: 7px;",
        }

        self._plot_window_sec = 1200.0
        self._plot_max_points = 6000
        self._plot_start_ts: Optional[int] = None
        self._plot_times: List[float] = []
        self._plot_gas: List[float] = []
        self._plot_temp: List[float] = []
        self._plot_hum: List[float] = []

        self._build_ui()

    def _build_ui(self) -> None:
        central = QWidget(self)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(12, 12, 12, 12)

        control_box = QGroupBox("Configuration")
        control_layout = QGridLayout(control_box)

        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["Replay CSV", "Tail CSV", "Subprocess"])
        self.mode_combo.currentTextChanged.connect(self.mode_changed.emit)

        self.csv_button = QPushButton("Select CSV")
        self.meta_button = QPushButton("Select Metadata")
        self.model_button = QPushButton("Select Model")

        self.csv_label = QLabel("CSV: <none>")
        self.meta_label = QLabel("Metadata: <none>")
        self.model_label = QLabel("Model: <none>")

        control_layout.addWidget(QLabel("Mode"), 0, 0)
        control_layout.addWidget(self.mode_combo, 0, 1)
        control_layout.addWidget(self.csv_button, 1, 0)
        control_layout.addWidget(self.csv_label, 1, 1)
        control_layout.addWidget(self.meta_button, 2, 0)
        control_layout.addWidget(self.meta_label, 2, 1)
        control_layout.addWidget(self.model_button, 3, 0)
        control_layout.addWidget(self.model_label, 3, 1)

        layout.addWidget(control_box)

        smoothing_box = QGroupBox("Smoothing / Hysteresis")
        smoothing_layout = QGridLayout(smoothing_box)

        self.ema_checkbox = QCheckBox("Enable EMA")
        self.ema_checkbox.setChecked(True)
        self.alpha_spin = QDoubleSpinBox()
        self.alpha_spin.setRange(0.0, 1.0)
        self.alpha_spin.setSingleStep(0.05)
        self.alpha_spin.setValue(0.3)

        self.threshold_spin = QDoubleSpinBox()
        self.threshold_spin.setRange(0.0, 1.0)
        self.threshold_spin.setSingleStep(0.05)
        self.threshold_spin.setValue(0.8)

        self.hold_spin = QSpinBox()
        self.hold_spin.setRange(1, 600)
        self.hold_spin.setValue(60)

        smoothing_layout.addWidget(self.ema_checkbox, 0, 0, 1, 2)
        smoothing_layout.addWidget(QLabel("EMA Alpha"), 1, 0)
        smoothing_layout.addWidget(self.alpha_spin, 1, 1)
        smoothing_layout.addWidget(QLabel("Threshold"), 2, 0)
        smoothing_layout.addWidget(self.threshold_spin, 2, 1)
        smoothing_layout.addWidget(QLabel("Hold (s)"), 3, 0)
        smoothing_layout.addWidget(self.hold_spin, 3, 1)

        layout.addWidget(smoothing_box)

        self.detector_box = QGroupBox("Detector Status")
        self.detector_layout = QGridLayout(self.detector_box)
        layout.addWidget(self.detector_box)

        plot_box = QGroupBox("Live Signals")
        plot_layout = QVBoxLayout(plot_box)
        self.figure = Figure(figsize=(6, 4), constrained_layout=True)
        self.canvas = FigureCanvas(self.figure)
        plot_layout.addWidget(self.canvas)

        self.ax_gas = self.figure.add_subplot(311)
        self.ax_temp = self.figure.add_subplot(312)
        self.ax_hum = self.figure.add_subplot(313)

        self.ax_gas.set_ylabel("Gas Ω")
        self.ax_temp.set_ylabel("Temp °C")
        self.ax_hum.set_ylabel("Humidity %")
        self.ax_hum.set_xlabel("Time (s)")

        self.line_gas, = self.ax_gas.plot([], [], color="#4C72B0")
        self.line_temp, = self.ax_temp.plot([], [], color="#DD8452")
        self.line_hum, = self.ax_hum.plot([], [], color="#55A868")

        layout.addWidget(plot_box)

        self.status_label = QLabel("Status: idle")
        layout.addWidget(self.status_label)

        button_row = QWidget()
        row_layout = QVBoxLayout(button_row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        self.start_button = QPushButton("Start")
        self.stop_button = QPushButton("Stop")
        self.stop_button.setEnabled(False)
        row_layout.addWidget(self.start_button)
        row_layout.addWidget(self.stop_button)
        layout.addWidget(button_row)

        self.setCentralWidget(central)

        self.csv_button.clicked.connect(self._pick_csv)
        self.meta_button.clicked.connect(self._pick_metadata)
        self.model_button.clicked.connect(self._pick_model)
        self.start_button.clicked.connect(self.start_requested.emit)
        self.stop_button.clicked.connect(self.stop_requested.emit)

    def _pick_csv(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Select CSV", filter="CSV Files (*.csv)")
        if path:
            self.csv_label.setText(f"CSV: {path}")
            self.csv_selected.emit(path)

    def _pick_metadata(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Select metadata.json", filter="JSON Files (*.json)")
        if path:
            self.meta_label.setText(f"Metadata: {path}")
            self.metadata_selected.emit(path)

    def _pick_model(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Select model.joblib", filter="Joblib (*.joblib)")
        if path:
            self.model_label.setText(f"Model: {path}")
            self.model_selected.emit(path)

    def set_classes(self, class_names: List[str]) -> None:
        while self.detector_layout.count():
            item = self.detector_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._class_widgets.clear()

        for row, name in enumerate(class_names):
            led = QLabel()
            led.setFixedSize(14, 14)
            led.setStyleSheet(self._led_styles["off"])
            text = QLabel(f"{name}: --")
            text.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            self.detector_layout.addWidget(led, row, 0)
            self.detector_layout.addWidget(text, row, 1)
            self._class_widgets[name] = (led, text)

        self.update_detections({name: 0.0 for name in class_names}, None)

    def update_detections(self, probabilities: Dict[str, float], winner: Optional[str], confidence: float = 0.0) -> None:
        if not self._class_widgets:
            return
        for name, (led, label) in self._class_widgets.items():
            prob = probabilities.get(name, 0.0)
            label.setText(f"{name}: {prob * 100:.1f}%")
            if winner and name == winner:
                led.setStyleSheet(self._led_styles["on"])
            else:
                led.setStyleSheet(self._led_styles["off"])

    def reset_run(self) -> None:
        self._plot_start_ts = None
        self._plot_times.clear()
        self._plot_gas.clear()
        self._plot_temp.clear()
        self._plot_hum.clear()
        self.line_gas.set_data([], [])
        self.line_temp.set_data([], [])
        self.line_hum.set_data([], [])
        for ax in (self.ax_gas, self.ax_temp, self.ax_hum):
            ax.relim()
            ax.autoscale_view()
        self.canvas.draw_idle()
        self.update_detections({name: 0.0 for name in self._class_widgets.keys()}, None)

    def append_samples(self, chunk: pd.DataFrame) -> None:
        if chunk.empty or "timestamp_ms" not in chunk.columns:
            return
        if self._plot_start_ts is None:
            self._plot_start_ts = int(chunk["timestamp_ms"].iloc[0])
        times = (chunk["timestamp_ms"].to_numpy(dtype=float) - self._plot_start_ts) / 1000.0
        gas = chunk.get("gas_resistance_ohms", pd.Series(dtype=float)).to_numpy(dtype=float)
        temp = chunk.get("temperature_C", pd.Series(dtype=float)).to_numpy(dtype=float)
        hum = chunk.get("humidity_pct", pd.Series(dtype=float)).to_numpy(dtype=float)

        self._plot_times.extend(times.tolist())
        self._plot_gas.extend(gas.tolist())
        self._plot_temp.extend(temp.tolist())
        self._plot_hum.extend(hum.tolist())

        if len(self._plot_times) > self._plot_max_points:
            excess = len(self._plot_times) - self._plot_max_points
            del self._plot_times[:excess]
            del self._plot_gas[:excess]
            del self._plot_temp[:excess]
            del self._plot_hum[:excess]

        if not self._plot_times:
            return

        end_time = self._plot_times[-1]
        start_time = max(0.0, end_time - self._plot_window_sec)

        self.line_gas.set_data(self._plot_times, self._plot_gas)
        self.line_temp.set_data(self._plot_times, self._plot_temp)
        self.line_hum.set_data(self._plot_times, self._plot_hum)

        for ax in (self.ax_gas, self.ax_temp, self.ax_hum):
            ax.set_xlim(start_time, max(end_time, start_time + 1.0))
            ax.relim()
            ax.autoscale_view(scalex=False, scaley=True)

        self.canvas.draw_idle()

    def set_status(self, text: str) -> None:
        self.status_label.setText(f"Status: {text}")

    def toggle_running(self, running: bool) -> None:
        self.start_button.setEnabled(not running)
        self.stop_button.setEnabled(running)
