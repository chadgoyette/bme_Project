from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

from PySide6.QtCore import QObject, QProcess, QProcessEnvironment

from .ui import WorkflowWindow


class WorkflowController(QObject):
    def __init__(self, view: WorkflowWindow) -> None:
        super().__init__(view)
        self.view = view
        self.workdir = Path.cwd()

        self.dataprep_process: Optional[QProcess] = None
        self.training_process: Optional[QProcess] = None

        self.view.dataprep_requested.connect(self._run_dataprep)
        self.view.training_requested.connect(self._run_training)

    # ------------------------------------------------------------------ Data prep
    def _run_dataprep(self, config: Dict[str, object]) -> None:
        if self.dataprep_process is not None:
            self.view.show_error("Data preparation is already running.")
            return

        data_root = Path(config["data_root"])
        out_dir = Path(config["out_dir"])
        if not data_root.exists():
            self.view.show_error(f"Data root does not exist: {data_root}")
            return
        out_dir.mkdir(parents=True, exist_ok=True)

        args = [
            "-m",
            "dataprep.build",
            "--data-root",
            str(data_root),
            "--out",
            str(out_dir),
            "--window-sec",
            str(config["window_sec"]),
            "--stride-sec",
            str(config["stride_sec"]),
            "--baseline-sec",
            str(config["baseline_sec"]),
            "--resample-hz",
            str(config["resample_hz"]),
            "--max-gap-sec",
            str(config["max_gap_sec"]),
        ]

        self.view.set_dataprep_running(True)
        self.view.set_dataprep_status("Status: running...")
        timestamp = datetime.utcnow().isoformat(timespec="seconds")
        self.view.append_log(f"=== Data Prep started {timestamp} ===")

        self.dataprep_process = self._launch_process(args, kind="dataprep")

    # ------------------------------------------------------------------ Training
    def _run_training(self, config: Dict[str, object]) -> None:
        if self.training_process is not None:
            self.view.show_error("Training is already running.")
            return

        features_path = Path(config["features_path"])
        output_dir = Path(config["output_dir"])

        if not features_path.exists():
            self.view.show_error(f"Features file not found: {features_path}")
            return
        group_col = str(config["group_col"]).strip()
        if not group_col:
            self.view.show_error("Group column cannot be blank.")
            return

        if output_dir.exists():
            if any(output_dir.iterdir()):
                self.view.show_error(f"Training output directory already contains files: {output_dir}")
                return
        else:
            output_dir.mkdir(parents=True, exist_ok=True)

        args = [
            "-m",
            "training.train",
            "--in",
            str(features_path),
            "--out",
            str(output_dir),
            "--group-col",
            group_col,
            "--model",
            str(config["model"]),
            "--cv-folds",
            str(config["cv_folds"]),
            "--seed",
            str(config["seed"]),
        ]

        self.view.set_training_running(True)
        self.view.set_training_status("Status: running...")
        timestamp = datetime.utcnow().isoformat(timespec="seconds")
        self.view.append_log(f"=== Training started {timestamp} ===")

        self.training_process = self._launch_process(args, kind="training")

    # ------------------------------------------------------------------ Process helpers
    def _launch_process(self, args: list[str], *, kind: str) -> QProcess:
        proc = QProcess(self)
        proc.setProgram(sys.executable)
        proc.setArguments(args)
        proc.setWorkingDirectory(str(self.workdir))
        proc.setProcessChannelMode(QProcess.SeparateChannels)
        proc.readyReadStandardOutput.connect(lambda: self._handle_output(proc, False))
        proc.readyReadStandardError.connect(lambda: self._handle_output(proc, True))
        proc.finished.connect(lambda code, status: self._process_finished(kind, proc, code, status))
        proc.errorOccurred.connect(lambda err: self._process_error(kind, err))
        env = QProcessEnvironment.systemEnvironment()
        proc.setProcessEnvironment(env)
        proc.start()
        return proc

    def _handle_output(self, proc: QProcess, is_stderr: bool) -> None:
        if is_stderr:
            data = proc.readAllStandardError().data().decode("utf-8", errors="replace")
        else:
            data = proc.readAllStandardOutput().data().decode("utf-8", errors="replace")
        self.view.append_log(data)

    def _process_finished(self, kind: str, proc: QProcess, exit_code: int, exit_status: QProcess.ExitStatus) -> None:
        self.view.flush_log()
        if kind == "dataprep":
            self.dataprep_process = None
            self.view.set_dataprep_running(False)
            if exit_status == QProcess.ExitStatus.NormalExit and exit_code == 0:
                self.view.set_dataprep_status("Status: completed")
                out_dir = Path(self.view.edit_prep_out.text())
                features_path = out_dir / "features.parquet"
                models_root = (self.workdir / "models").resolve()
                models_root.mkdir(parents=True, exist_ok=True)
                self.view.set_training_defaults(features_path, models_root)
            else:
                self.view.set_dataprep_status("Status: failed")
        elif kind == "training":
            self.training_process = None
            self.view.set_training_running(False)
            if exit_status == QProcess.ExitStatus.NormalExit and exit_code == 0:
                self.view.set_training_status("Status: completed")
            else:
                self.view.set_training_status("Status: failed")

    def _process_error(self, kind: str, error: QProcess.ProcessError) -> None:
        message = f"{kind.capitalize()} process error: {error}"
        self.view.append_log(message)
        if kind == "dataprep":
            self.dataprep_process = None
            self.view.set_dataprep_running(False)
            self.view.set_dataprep_status("Status: failed")
        else:
            self.training_process = None
            self.view.set_training_running(False)
            self.view.set_training_status("Status: failed")
        self.view.show_error(message)

