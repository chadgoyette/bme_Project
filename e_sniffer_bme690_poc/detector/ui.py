from __future__ import annotations

from typing import Dict, List, Optional, Tuple

import pandas as pd
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from collector.profiles import Profile, list_default_profiles


class DetectorWindow(QMainWindow):
    model_selected = Signal(str)
    metadata_selected = Signal(str)
    profile_changed = Signal(Profile)
    start_requested = Signal()
    stop_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("E-Sniffer Detector")

        self._profile_items: Dict[str, Profile] = {}
        self._class_widgets: Dict[str, Tuple[QLabel, QLabel]] = {}
        self._led_styles = {
            "off": "background-color: #6c6c6c; border-radius: 7px;",
            "on": "background-color: #2ecc71; border-radius: 7px;",
        }

        self._plot_window_sec = 1200.0
        self._plot_max_points = 6000
        self._plot_start_ms: Optional[int] = None
        self._data_times: List[float] = []
        self._gas_values: List[float] = []
        self._temp_values: List[float] = []
        self._hum_values: List[float] = []

        self._build_ui()
        self._load_default_profiles()

    def _build_ui(self) -> None:
        central = QWidget(self)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        config_group = QGroupBox("Configuration")
        config_layout = QGridLayout(config_group)
        config_layout.setHorizontalSpacing(12)

        self.btn_model = QPushButton("Load Model")
        self.label_model = QLabel("Model: <none>")
        self.btn_metadata = QPushButton("Load Metadata")
        self.label_metadata = QLabel("Metadata: <none>")

        self.combo_profile = QComboBox()
        self.btn_load_profile = QPushButton("Load Profile...")
        self.label_profile = QLabel("Profile: <none>")

        config_layout.addWidget(self.btn_model, 0, 0)
        config_layout.addWidget(self.label_model, 0, 1)
        config_layout.addWidget(self.btn_metadata, 1, 0)
        config_layout.addWidget(self.label_metadata, 1, 1)
        config_layout.addWidget(QLabel("Profile"), 2, 0)
        profile_row = QHBoxLayout()
        profile_row.setContentsMargins(0, 0, 0, 0)
        profile_row.addWidget(self.combo_profile)
        profile_row.addWidget(self.btn_load_profile)
        profile_widget = QWidget()
        profile_widget.setLayout(profile_row)
        config_layout.addWidget(profile_widget, 2, 1)
        config_layout.addWidget(self.label_profile, 3, 1)

        config_layout.addWidget(QLabel("Capture cycles"), 4, 0)
        self.spin_cycles = QSpinBox()
        self.spin_cycles.setRange(1, 10000)
        self.spin_cycles.setValue(120)
        config_layout.addWidget(self.spin_cycles, 4, 1)

        config_layout.addWidget(QLabel("Skip warmup cycles"), 5, 0)
        self.spin_skip = QSpinBox()
        self.spin_skip.setRange(0, 1000)
        self.spin_skip.setValue(3)
        config_layout.addWidget(self.spin_skip, 5, 1)

        layout.addWidget(config_group)

        status_group = QGroupBox("Run Status")
        status_layout = QGridLayout(status_group)
        status_layout.setHorizontalSpacing(10)
        status_layout.setVerticalSpacing(6)
        self.label_status = QLabel("Status: idle")
        self.label_cycle = QLabel("Cycle: -")
        self.label_step = QLabel("Step: -")
        self.label_command = QLabel("Heater: -")
        self.label_gas = QLabel("Gas: -")
        self.label_temp = QLabel("Temp: -")
        self.label_hum = QLabel("Humidity: -")
        self.label_pressure = QLabel("Pressure: -")

        status_layout.addWidget(self.label_status, 0, 0, 1, 2)
        status_layout.addWidget(self.label_cycle, 1, 0)
        status_layout.addWidget(self.label_step, 1, 1)
        status_layout.addWidget(self.label_command, 2, 0, 1, 2)
        status_layout.addWidget(self.label_gas, 3, 0)
        status_layout.addWidget(self.label_temp, 3, 1)
        status_layout.addWidget(self.label_hum, 4, 0)
        status_layout.addWidget(self.label_pressure, 4, 1)

        layout.addWidget(status_group)

        detector_group = QGroupBox("Detector Output")
        self.detector_layout = QGridLayout(detector_group)
        layout.addWidget(detector_group)

        plot_group = QGroupBox("Live Signals")
        plot_layout = QVBoxLayout(plot_group)
        self.figure = Figure(figsize=(6, 4), constrained_layout=True)
        self.canvas = FigureCanvas(self.figure)
        plot_layout.addWidget(self.canvas)

        self.ax_gas = self.figure.add_subplot(311)
        self.ax_temp = self.figure.add_subplot(312)
        self.ax_hum = self.figure.add_subplot(313)

        self.ax_gas.set_ylabel("Gas (ohm)")
        self.ax_temp.set_ylabel("Temp (deg C)")
        self.ax_hum.set_ylabel("Humidity (%)")
        self.ax_hum.set_xlabel("Time (s)")

        (self.line_gas,) = self.ax_gas.plot([], [], color="#1f77b4")
        (self.line_temp,) = self.ax_temp.plot([], [], color="#ff7f0e")
        (self.line_hum,) = self.ax_hum.plot([], [], color="#2ca02c")

        layout.addWidget(plot_group)

        buttons = QWidget()
        buttons_layout = QHBoxLayout(buttons)
        buttons_layout.setContentsMargins(0, 0, 0, 0)
        buttons_layout.setSpacing(8)
        self.btn_start = QPushButton("Start")
        self.btn_stop = QPushButton("Stop")
        self.btn_stop.setEnabled(False)
        buttons_layout.addWidget(self.btn_start)
        buttons_layout.addWidget(self.btn_stop)
        layout.addWidget(buttons)

        self.setCentralWidget(central)

        self.btn_model.clicked.connect(self._pick_model)
        self.btn_metadata.clicked.connect(self._pick_metadata)
        self.btn_load_profile.clicked.connect(self._pick_profile)
        self.btn_start.clicked.connect(self.start_requested.emit)
        self.btn_stop.clicked.connect(self.stop_requested.emit)
        self.combo_profile.currentIndexChanged.connect(self._on_profile_changed)

    def _load_default_profiles(self) -> None:
        self.combo_profile.blockSignals(True)
        self.combo_profile.clear()
        self._profile_items.clear()
        for profile in list_default_profiles():
            text = profile.name
            self.combo_profile.addItem(text, profile)
            self._profile_items[text] = profile
        self.combo_profile.blockSignals(False)
        if self.combo_profile.count():
            self.combo_profile.setCurrentIndex(0)
            profile = self.combo_profile.currentData()
            if isinstance(profile, Profile):
                self._set_profile(profile)

    def _pick_model(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Select model.joblib", filter="Joblib (*.joblib)")
        if path:
            self.label_model.setText(f"Model: {path}")
            self.model_selected.emit(path)

    def _pick_metadata(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Select metadata.json", filter="JSON Files (*.json)")
        if path:
            self.label_metadata.setText(f"Metadata: {path}")
            self.metadata_selected.emit(path)

    def _pick_profile(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Select profile", filter="Profiles (*.bmeprofile)")
        if not path:
            return
        try:
            profile = Profile.load(path, read_only=True)
        except Exception as exc:
            QMessageBox.critical(self, "Profile error", f"Failed to load profile:\n{exc}")
            return
        display_name = f"Custom: {profile.name}"
        self.combo_profile.addItem(display_name, profile)
        self.combo_profile.setCurrentIndex(self.combo_profile.count() - 1)
        self._profile_items[display_name] = profile
        self._set_profile(profile)
        self.profile_changed.emit(profile)

    def _on_profile_changed(self, index: int) -> None:
        profile = self.combo_profile.itemData(index)
        if isinstance(profile, Profile):
            self._set_profile(profile)
            self.profile_changed.emit(profile)

    def _set_profile(self, profile: Profile) -> None:
        steps = ", ".join(f"{step.temp_c} deg C/{step.duration_ms} ms" for step in profile.steps)
        self.label_profile.setText(
            f"Profile: {profile.name} | Backend {profile.backend} | Steps: {steps}"
        )

    def cycles_target(self) -> int:
        return self.spin_cycles.value()

    def skip_cycles(self) -> int:
        return self.spin_skip.value()

    def set_status(self, text: str) -> None:
        self.label_status.setText(f"Status: {text}")

    def toggle_running(self, running: bool) -> None:
        self.btn_start.setEnabled(not running)
        self.btn_stop.setEnabled(running)
        self.combo_profile.setEnabled(not running)
        self.btn_load_profile.setEnabled(not running)
        self.spin_cycles.setEnabled(not running)
        self.spin_skip.setEnabled(not running)

    def set_step_status(
        self,
        cycle_label: str,
        step_label: str,
        heater_text: str,
        gas_text: str,
        temp_text: str,
        hum_text: str,
        pressure_text: str,
    ) -> None:
        self.label_cycle.setText(cycle_label)
        self.label_step.setText(step_label)
        self.label_command.setText(heater_text)
        self.label_gas.setText(gas_text)
        self.label_temp.setText(temp_text)
        self.label_hum.setText(hum_text)
        self.label_pressure.setText(pressure_text)

    def set_classes(self, class_names: List[str]) -> None:
        while self.detector_layout.count():
            item = self.detector_layout.takeAt(0)
            widget = item.widget()
            if widget:
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
        if not class_names:
            placeholder = QLabel("No classes loaded")
            self.detector_layout.addWidget(placeholder, 0, 0)

    def update_detections(self, probabilities: Dict[str, float], winner: Optional[str]) -> None:
        if not self._class_widgets:
            return
        for name, (led, label) in self._class_widgets.items():
            prob = probabilities.get(name, 0.0)
            label.setText(f"{name}: {prob * 100:.1f}%")
            led.setStyleSheet(self._led_styles["on"] if winner and name == winner else self._led_styles["off"])

    def reset_plots(self) -> None:
        self._plot_start_ms = None
        self._data_times.clear()
        self._gas_values.clear()
        self._temp_values.clear()
        self._hum_values.clear()
        self.line_gas.set_data([], [])
        self.line_temp.set_data([], [])
        self.line_hum.set_data([], [])
        for ax in (self.ax_gas, self.ax_temp, self.ax_hum):
            ax.relim()
            ax.autoscale_view()
        self.canvas.draw_idle()

    def append_samples(self, chunk: pd.DataFrame) -> None:
        if chunk.empty or "timestamp_ms" not in chunk.columns:
            return
        if self._plot_start_ms is None:
            self._plot_start_ms = int(chunk["timestamp_ms"].iloc[0])
        times = (chunk["timestamp_ms"].to_numpy(dtype=float) - self._plot_start_ms) / 1000.0
        gas = chunk.get("gas_resistance_ohms", pd.Series(dtype=float)).to_numpy(dtype=float)
        temp = chunk.get("temperature_C", pd.Series(dtype=float)).to_numpy(dtype=float)
        hum = chunk.get("humidity_pct", pd.Series(dtype=float)).to_numpy(dtype=float)

        self._data_times.extend(times.tolist())
        self._gas_values.extend(gas.tolist())
        self._temp_values.extend(temp.tolist())
        self._hum_values.extend(hum.tolist())

        if len(self._data_times) > self._plot_max_points:
            excess = len(self._data_times) - self._plot_max_points
            del self._data_times[:excess]
            del self._gas_values[:excess]
            del self._temp_values[:excess]
            del self._hum_values[:excess]

        if not self._data_times:
            return

        end_time = self._data_times[-1]
        start_time = max(0.0, end_time - self._plot_window_sec)
        self.line_gas.set_data(self._data_times, self._gas_values)
        self.line_temp.set_data(self._data_times, self._temp_values)
        self.line_hum.set_data(self._data_times, self._hum_values)

        for ax in (self.ax_gas, self.ax_temp, self.ax_hum):
            ax.set_xlim(start_time, max(end_time, start_time + 1.0))
            ax.relim()
            ax.autoscale_view(scalex=False, scaley=True)

        self.canvas.draw_idle()

