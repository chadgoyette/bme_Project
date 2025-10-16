from __future__ import annotations

import math
import time
from collections import deque
import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Callable, Deque, Dict, Iterable, List, Optional

from .profiles import Profile, ProfileStep, profile_from_default
from .runtime import CollectorRunner, Metadata, RunConfig, build_backend


TICK_DURATION_MS = 140


class ProfileEditorDialog(tk.Toplevel):
    def __init__(self, master: tk.Misc, profile: Profile) -> None:
        super().__init__(master)
        self.title("Edit Profile")
        self.resizable(False, False)
        self.profile = profile.clone(name=profile.name, read_only=False)
        self.result: Optional[Profile] = None

        self.var_name = tk.StringVar(value=self.profile.name)
        self.var_backend = tk.StringVar(value=self.profile.backend)
        self.var_i2c = tk.StringVar(value=self.profile.i2c_addr)
        self.var_notes = tk.StringVar(value=self.profile.notes)

        container = ttk.Frame(self, padding=12)
        container.grid(row=0, column=0, sticky="nsew")

        ttk.Label(container, text="Profile name").grid(row=0, column=0, sticky="w")
        ttk.Entry(container, textvariable=self.var_name, width=32).grid(row=0, column=1, sticky="ew")

        ttk.Label(container, text="Backend").grid(row=1, column=0, sticky="w")
        ttk.Combobox(
            container,
            textvariable=self.var_backend,
            values=["bme68x_i2c", "coines"],
            state="readonly",
            width=18,
        ).grid(row=1, column=1, sticky="w")

        ttk.Label(container, text="I2C address").grid(row=2, column=0, sticky="w")
        ttk.Entry(container, textvariable=self.var_i2c, width=10).grid(row=2, column=1, sticky="w")

        ttk.Label(container, text="Notes").grid(row=3, column=0, sticky="nw")
        notes_entry = ttk.Entry(container, textvariable=self.var_notes, width=40)
        notes_entry.grid(row=3, column=1, sticky="ew")

        self.tree = ttk.Treeview(
            container,
            columns=("temp", "ticks", "ms"),
            show="headings",
            height=10,
            selectmode="browse",
        )
        self.tree.heading("temp", text="Temp (deg C)")
        self.tree.heading("ticks", text="Ticks")
        self.tree.heading("ms", text="Approx (ms)")
        self.tree.grid(row=4, column=0, columnspan=2, pady=8, sticky="nsew")

        button_frame = ttk.Frame(container)
        button_frame.grid(row=5, column=0, columnspan=2, pady=4)
        ttk.Button(button_frame, text="Add Step", command=self._add_step).grid(row=0, column=0, padx=4)
        ttk.Button(button_frame, text="Remove Step", command=self._remove_step).grid(row=0, column=1, padx=4)

        action_frame = ttk.Frame(container)
        action_frame.grid(row=6, column=0, columnspan=2, pady=(10, 0))
        ttk.Button(action_frame, text="Cancel", command=self.destroy).grid(row=0, column=0, padx=6)
        ttk.Button(action_frame, text="Save", command=self._on_save).grid(row=0, column=1, padx=6)

        container.columnconfigure(1, weight=1)
        self.tree.column("temp", width=110, anchor="center")
        self.tree.column("ticks", width=100, anchor="center")
        self.tree.column("ms", width=120, anchor="center")

        self._refresh_steps()

    def _refresh_steps(self) -> None:
        for iid in self.tree.get_children():
            self.tree.delete(iid)
        for idx, step in enumerate(self.profile.steps, start=1):
            self.tree.insert(
                "",
                "end",
                iid=str(idx),
                values=(step.temp_c, step.ticks, step.duration_ms),
            )

    def _add_step(self) -> None:
        StepDialog(self, callback=self._insert_step)

    def _insert_step(self, temp_c: int, ticks: int) -> None:
        self.profile.steps.append(ProfileStep(temp_c=temp_c, ticks=ticks))
        self._refresh_steps()

    def _remove_step(self) -> None:
        selection = self.tree.selection()
        if not selection:
            return
        index = int(selection[0]) - 1
        if 0 <= index < len(self.profile.steps):
            del self.profile.steps[index]
            self._refresh_steps()

    def _on_save(self) -> None:
        self.profile.name = self.var_name.get().strip() or "Untitled profile"
        self.profile.backend = self.var_backend.get().strip() or "bme68x_i2c"
        self.profile.i2c_addr = self.var_i2c.get().strip() or "0x76"
        self.profile.notes = self.var_notes.get()
        try:
            self.profile.validate()
        except ValueError as exc:
            messagebox.showerror("Validation error", str(exc), parent=self)
            return
        self.result = self.profile
        self.destroy()


class StepDialog(tk.Toplevel):
    def __init__(self, master: tk.Misc, callback: Callable[[int, int], None]) -> None:
        super().__init__(master)
        self.title("Add Step")
        self.resizable(False, False)
        self.callback = callback

        self.var_temp = tk.IntVar(value=200)
        self.var_ticks = tk.IntVar(value=1)
        self.var_ms = tk.StringVar()

        frame = ttk.Frame(self, padding=10)
        frame.grid(row=0, column=0)

        ttk.Label(frame, text="Temp (deg C)").grid(row=0, column=0, sticky="w")
        ttk.Entry(frame, textvariable=self.var_temp, width=8).grid(row=0, column=1, padx=4)

        ttk.Label(frame, text="Ticks").grid(row=1, column=0, sticky="w")
        ttk.Entry(frame, textvariable=self.var_ticks, width=8).grid(row=1, column=1, padx=4)

        ttk.Label(frame, textvariable=self.var_ms).grid(row=2, column=0, columnspan=2, sticky="w")

        buttons = ttk.Frame(frame)
        buttons.grid(row=3, column=0, columnspan=2, pady=(8, 0))
        ttk.Button(buttons, text="Cancel", command=self.destroy).grid(row=0, column=0, padx=4)
        ttk.Button(buttons, text="Add", command=self._commit).grid(row=0, column=1, padx=4)

        self._update_display()
        self.var_ticks.trace_add("write", lambda *_: self._update_display())

    def _update_display(self) -> None:
        ticks = max(0, self.var_ticks.get())
        self.var_ms.set(f"≈ {ticks * TICK_DURATION_MS} ms (1 tick = {TICK_DURATION_MS} ms)")

    def _commit(self) -> None:
        try:
            step = ProfileStep(temp_c=int(self.var_temp.get()), ticks=max(1, int(self.var_ticks.get())))
            step.validate()
        except ValueError as exc:
            messagebox.showerror("Invalid step", str(exc), parent=self)
            return
        self.callback(step.temp_c, step.ticks)
        self.destroy()


class CollectorApp:
    def __init__(
        self,
        initial_profile: Profile,
        defaults: Iterable[Profile],
        on_profile_selected: Optional[Callable[[Profile], None]] = None,
    ) -> None:
        self.root = tk.Tk()
        self.root.title("BME690 Collector")

        self.profiles: Dict[str, Profile] = {}
        self.active_profile_key: Optional[str] = None
        self.on_profile_selected = on_profile_selected

        self.runner: Optional[CollectorRunner] = None
        self.runner_thread: Optional[threading.Thread] = None
        self.status_queue: "queue.Queue[dict]" = queue.Queue()
        self.progress_active = False
        self.progress_start_time: Optional[float] = None
        self.progress_total_ms: float = 1.0
        self.progress_cycle_total_ms: float = 0.0
        self.progress_cycle_prefix: List[float] = [0.0]
        self.progress_inferred_ms: float = 0.0
        self.progress_warmup_ms: float = 0.0
        self.graph_data: Deque[tuple[float, float]] = deque()
        self.graph_window_seconds = 120.0
        self.graph_redraw_pending = False
        self.graph_placeholder: Optional[int] = None

        self._build_layout()
        self._reset_progress()
        self._reset_graph()
        for default in defaults:
            self._register_profile(default, readonly=True)
        self._register_profile(initial_profile, readonly=initial_profile.read_only)
        self._select_profile(initial_profile)
        self._poll_status_queue()

    def _build_layout(self) -> None:
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)

        container = ttk.Frame(self.root, padding=12)
        container.grid(row=0, column=0, sticky="nsew")
        container.columnconfigure(0, weight=1)
        container.columnconfigure(1, weight=1)

        self._build_profile_panel(container)
        self._build_run_panel(container)

    # --------------------------------------------------------------------- Profiles
    def _build_profile_panel(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text="Profiles", padding=8)
        frame.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        frame.columnconfigure(0, weight=1)

        self.combo_profile = ttk.Combobox(frame, state="readonly")
        self.combo_profile.grid(row=0, column=0, columnspan=3, sticky="ew")
        self.combo_profile.bind("<<ComboboxSelected>>", self._on_profile_change)

        ttk.Button(frame, text="New", command=self._new_profile).grid(row=1, column=0, pady=4, sticky="ew")
        ttk.Button(frame, text="Duplicate", command=self._duplicate_profile).grid(row=1, column=1, pady=4, sticky="ew")
        ttk.Button(frame, text="Edit", command=self._edit_profile).grid(row=1, column=2, pady=4, sticky="ew")
        ttk.Button(frame, text="Delete", command=self._delete_profile).grid(row=2, column=0, pady=4, sticky="ew")
        ttk.Button(frame, text="Import", command=self._import_profile).grid(row=2, column=1, pady=4, sticky="ew")
        ttk.Button(frame, text="Export", command=self._export_profile).grid(row=2, column=2, pady=4, sticky="ew")

        self.summary_text = tk.Text(frame, width=42, height=18, state="disabled")
        self.summary_text.grid(row=3, column=0, columnspan=3, pady=(8, 0), sticky="nsew")
        frame.rowconfigure(3, weight=1)

    def _register_profile(self, profile: Profile, readonly: bool = False) -> None:
        display_name = profile.name if not readonly else f"{profile.name} (default)"
        unique_name = display_name
        counter = 1
        while unique_name in self.profiles:
            counter += 1
            unique_name = f"{display_name} #{counter}"
        profile.read_only = readonly
        self.profiles[unique_name] = profile
        self._refresh_profile_combo(unique_name)

    def _refresh_profile_combo(self, select: Optional[str] = None) -> None:
        names = list(self.profiles.keys())
        self.combo_profile["values"] = names
        if select:
            self.combo_profile.set(select)
            self.active_profile_key = select
            self._update_summary()
            if self.on_profile_selected:
                self.on_profile_selected(self.profiles[select])

    def _select_profile(self, profile: Profile) -> None:
        for key, value in self.profiles.items():
            if value is profile:
                self.combo_profile.set(key)
                self.active_profile_key = key
                self._update_summary()
                if self.on_profile_selected:
                    self.on_profile_selected(profile)
                break

    def _on_profile_change(self, _event=None) -> None:
        key = self.combo_profile.get()
        if key and key in self.profiles:
            self.active_profile_key = key
            self._update_summary()
            if self.on_profile_selected:
                self.on_profile_selected(self.profiles[key])

    def _current_profile(self) -> Optional[Profile]:
        if self.active_profile_key is None:
            return None
        return self.profiles.get(self.active_profile_key)

    def _update_summary(self) -> None:
        profile = self._current_profile()
        self.summary_text.configure(state="normal")
        self.summary_text.delete("1.0", "end")
        if profile:
            self.summary_text.insert("end", f"Name: {profile.name}\n")
            self.summary_text.insert("end", f"Backend: {profile.backend}\n")
            self.summary_text.insert("end", f"I2C: {profile.i2c_addr}\n")
            self.summary_text.insert(
                "end",
                f"Estimated cycle: {profile.estimated_cycle_length_sec():.2f} s\n\n",
            )
            self.summary_text.insert("end", "Steps:\n")
            for idx, step in enumerate(profile.steps, start=1):
                self.summary_text.insert(
                    "end",
                    f"  {idx}. {step.temp_c} °C / {step.ticks} ticks ({step.duration_ms} ms)\n",
                )
            if profile.notes:
                self.summary_text.insert("end", f"\nNotes: {profile.notes}\n")
        self.summary_text.configure(state="disabled")

    def _new_profile(self) -> None:
        profile = Profile(
            name="New profile",
            version=1,
            backend="bme68x_i2c",
            i2c_addr="0x76",
            steps=[ProfileStep(temp_c=200, ticks=1)],
            cycle_target_sec=profile_from_default("Broad Sweep (meat)").cycle_target_sec,
        )
        dialog = ProfileEditorDialog(self.root, profile)
        self.root.wait_window(dialog)
        if dialog.result:
            self._register_profile(dialog.result, readonly=False)
            self._refresh_profile_combo(self.active_profile_key)

    def _duplicate_profile(self) -> None:
        profile = self._current_profile()
        if not profile:
            return
        duplicate = profile.clone()
        duplicate.read_only = False
        dialog = ProfileEditorDialog(self.root, duplicate)
        self.root.wait_window(dialog)
        if dialog.result:
            self._register_profile(dialog.result, readonly=False)
            self._refresh_profile_combo(self.active_profile_key)

    def _edit_profile(self) -> None:
        profile = self._current_profile()
        if not profile or profile.read_only:
            messagebox.showinfo("Edit profile", "Select a non-default profile to edit.")
            return
        dialog = ProfileEditorDialog(self.root, profile)
        self.root.wait_window(dialog)
        if dialog.result:
            self.profiles[self.active_profile_key] = dialog.result
            self._refresh_profile_combo(self.active_profile_key)

    def _delete_profile(self) -> None:
        profile = self._current_profile()
        if not profile or profile.read_only:
            messagebox.showwarning("Delete profile", "Cannot delete default profiles.")
            return
        if messagebox.askyesno("Delete profile", f"Delete '{profile.name}'?"):
            del self.profiles[self.active_profile_key]
            remaining = list(self.profiles.keys())
            if remaining:
                self.combo_profile.set(remaining[0])
                self.active_profile_key = remaining[0]
            else:
                self.combo_profile.set("")
                self.active_profile_key = None
            self._update_summary()

    def _import_profile(self, _event=None) -> None:
        path = filedialog.askopenfilename(filetypes=[("BME Profiles", "*.bmeprofile"), ("JSON", "*.json")])
        if not path:
            return
        try:
            profile = Profile.load(Path(path))
        except Exception as exc:
            messagebox.showerror("Import failed", str(exc))
            return
        profile.path = Path(path)
        self._register_profile(profile, readonly=profile.read_only)
        self._select_profile(profile)

    def _export_profile(self) -> None:
        profile = self._current_profile()
        if not profile:
            return
        path = filedialog.asksaveasfilename(defaultextension=".bmeprofile", filetypes=[("BME Profiles", "*.bmeprofile")])
        if not path:
            return
        try:
            profile.save(Path(path))
        except Exception as exc:
            messagebox.showerror("Export failed", str(exc))

    # ----------------------------------------------------------------------- Run
    def _build_run_panel(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text="Run Collection", padding=8)
        frame.grid(row=0, column=1, sticky="nsew")
        frame.columnconfigure(1, weight=1)

        ttk.Label(frame, text="Sample name").grid(row=0, column=0, sticky="w")
        self.entry_sample = ttk.Entry(frame)
        self.entry_sample.grid(row=0, column=1, sticky="ew")

        ttk.Label(frame, text="Specimen ID").grid(row=1, column=0, sticky="w")
        self.entry_specimen = ttk.Entry(frame)
        self.entry_specimen.grid(row=1, column=1, sticky="ew")

        ttk.Label(frame, text="Storage").grid(row=2, column=0, sticky="w")
        self.combo_storage = ttk.Combobox(frame, state="readonly", values=["refrigerated", "countertop", "frozen", "other"])
        self.combo_storage.current(0)
        self.combo_storage.grid(row=2, column=1, sticky="ew")

        ttk.Label(frame, text="Notes").grid(row=3, column=0, sticky="nw")
        self.text_notes = tk.Text(frame, height=4)
        self.text_notes.grid(row=3, column=1, sticky="ew")

        ttk.Label(frame, text="Output folder").grid(row=4, column=0, sticky="w")
        self.var_output_dir = tk.StringVar(value=str((Path.cwd() / "logs").resolve()))
        out_frame = ttk.Frame(frame)
        out_frame.columnconfigure(0, weight=1)
        out_frame.grid(row=4, column=1, sticky="ew")
        self.entry_output = ttk.Entry(out_frame, textvariable=self.var_output_dir)
        self.entry_output.grid(row=0, column=0, sticky="ew")
        ttk.Button(out_frame, text="Browse...", command=self._pick_output_dir).grid(row=0, column=1, padx=(6, 0))

        ttk.Label(frame, text="Cycles to capture").grid(row=5, column=0, sticky="w")
        self.spin_cycles = tk.Spinbox(frame, from_=1, to=500, increment=1, width=8)
        self.spin_cycles.delete(0, "end")
        self.spin_cycles.insert(0, "10")
        self.spin_cycles.grid(row=5, column=1, sticky="w")

        ttk.Label(frame, text="Skip first cycles").grid(row=6, column=0, sticky="w")
        self.spin_skip = tk.Spinbox(frame, from_=0, to=100, increment=1, width=8)
        self.spin_skip.delete(0, "end")
        self.spin_skip.insert(0, "3")
        self.spin_skip.grid(row=6, column=1, sticky="w")

        self.label_error = ttk.Label(frame, text="", foreground="red")
        self.label_error.grid(row=7, column=0, columnspan=2, sticky="w")

        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=8, column=0, columnspan=2, pady=6)
        self.btn_start = ttk.Button(btn_frame, text="Start", command=self._toggle_run)
        self.btn_start.grid(row=0, column=0, padx=4)
        self.btn_stop = ttk.Button(btn_frame, text="Stop", command=self._stop_run, state="disabled")
        self.btn_stop.grid(row=0, column=1, padx=4)

        status = ttk.LabelFrame(frame, text="Status", padding=6)
        status.grid(row=9, column=0, columnspan=2, sticky="ew")
        status.columnconfigure(0, weight=1)
        status.columnconfigure(1, weight=1)

        self.label_cycle = ttk.Label(status, text="Cycle: -")
        self.label_step = ttk.Label(status, text="Step: -")
        self.label_command = ttk.Label(status, text="Heater: -")
        self.label_gas = ttk.Label(status, text="Gas: -")
        self.label_temp = ttk.Label(status, text="Temp: -")
        self.label_humidity = ttk.Label(status, text="Humidity: -")
        self.label_pressure = ttk.Label(status, text="Pressure: -")

        self.label_cycle.grid(row=0, column=0, sticky="w")
        self.label_step.grid(row=0, column=1, sticky="w")
        self.label_command.grid(row=1, column=0, columnspan=2, sticky="w")
        self.label_gas.grid(row=2, column=0, sticky="w")
        self.label_temp.grid(row=2, column=1, sticky="w")
        self.label_humidity.grid(row=3, column=0, sticky="w")
        self.label_pressure.grid(row=3, column=1, sticky="w")
        self.progress_var = tk.DoubleVar(value=0.0)
        self.progress_bar = ttk.Progressbar(status, variable=self.progress_var, maximum=1.0)
        self.progress_bar.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(8, 2))
        self.label_eta = ttk.Label(status, text="ETA: --")
        self.label_eta.grid(row=5, column=0, columnspan=2, sticky="w")

        graph = ttk.LabelFrame(frame, text="Gas Resistance (last 2 min)", padding=6)
        graph.grid(row=10, column=0, columnspan=2, sticky="nsew", pady=(8, 0))
        graph.columnconfigure(0, weight=1)
        graph.rowconfigure(0, weight=1)
        self.graph_canvas = tk.Canvas(graph, height=200, background=self.root.cget("background"), highlightthickness=0)
        self.graph_canvas.grid(row=0, column=0, sticky="nsew")
        self.graph_canvas.bind("<Configure>", lambda _event: self._schedule_graph_redraw())
        frame.rowconfigure(10, weight=1)

    def _pick_output_dir(self) -> None:
        current = Path(self.var_output_dir.get()).expanduser()
        initial = current if current.exists() else Path.cwd()
        selected = filedialog.askdirectory(parent=self.root, initialdir=str(initial), title="Select output folder")
        if selected:
            self.var_output_dir.set(selected)

    def _toggle_run(self) -> None:
        if self.runner_thread and self.runner_thread.is_alive():
            self._stop_run()
        else:
            self._start_run()

    def _start_run(self) -> None:
        profile = self._current_profile()
        if not profile:
            self._set_error("Select a profile before starting.")
            return
        try:
            profile.validate()
        except ValueError as exc:
            self._set_error(str(exc))
            return

        metadata = self._collect_metadata()
        if metadata is None:
            return

        try:
            cycles_target = max(1, int(float(self.spin_cycles.get())))
            skip_cycles = max(0, int(float(self.spin_skip.get())))
        except ValueError:
            self._set_error("Cycles must be numeric.")
            return

        output_root_text = self.var_output_dir.get().strip()
        output_root = Path(output_root_text).expanduser() if output_root_text else Path.cwd() / "logs"
        try:
            output_root.mkdir(parents=True, exist_ok=True)
        except Exception as exc:
            self._set_error(f"Unable to access output folder: {exc}")
            return
        self.var_output_dir.set(str(output_root))

        try:
            backend = build_backend(profile)
        except Exception as exc:
            self._set_error(str(exc))
            return

        self._drain_status_queue()
        self._reset_graph()
        self._initialize_progress(profile, cycles_target, skip_cycles)
        run_config = RunConfig(
            profile=profile,
            metadata=metadata,
            cycles_target=cycles_target,
            backend=backend,
            profile_hash=profile.hash(),
            skip_cycles=skip_cycles,
            output_root=output_root,
            status_callback=lambda row: self.status_queue.put(row),
        )
        self.runner = CollectorRunner(run_config)
        self.runner_thread = threading.Thread(target=self._run_worker, daemon=True)
        self.runner_thread.start()
        self.btn_start.configure(state="disabled")
        self.btn_stop.configure(state="normal")
        self._set_error("")

    def _stop_run(self) -> None:
        if self.runner:
            self.runner.config.stop()
        self._reset_progress()
        self.btn_stop.configure(state="disabled")
        self.btn_start.configure(state="normal")

    def _run_worker(self) -> None:
        import traceback

        try:
            path = self.runner.run() if self.runner else None
            self.status_queue.put({"__complete__": path})
        except Exception:
            self.status_queue.put({"__error__": traceback.format_exc()})

    def _collect_metadata(self) -> Optional[Metadata]:
        payload = {
            "sample_name": self.entry_sample.get().strip(),
            "specimen_id": self.entry_specimen.get().strip(),
            "storage": self.combo_storage.get().strip(),
            "notes": self.text_notes.get("1.0", "end").strip(),
        }
        try:
            return Metadata.from_mapping(payload)
        except ValueError as exc:
            self._set_error(str(exc))
            return None

    def _set_error(self, message: str) -> None:
        self.label_error.configure(text=message)

    def _reset_progress(self) -> None:
        self.progress_active = False
        self.progress_start_time = None
        self.progress_total_ms = 1.0
        self.progress_cycle_total_ms = 0.0
        self.progress_cycle_prefix = [0.0]
        self.progress_inferred_ms = 0.0
        self.progress_warmup_ms = 0.0
        if hasattr(self, "progress_var"):
            self.progress_var.set(0.0)
        if hasattr(self, "label_eta"):
            self.label_eta.configure(text="ETA: --")

    def _reset_graph(self) -> None:
        self.graph_data.clear()
        self.graph_redraw_pending = False
        if hasattr(self, "graph_canvas"):
            canvas = self.graph_canvas
            canvas.delete("all")
            width = max(canvas.winfo_width(), canvas.winfo_reqwidth(), 1)
            height = max(canvas.winfo_height(), canvas.winfo_reqheight(), 1)
            self.graph_placeholder = canvas.create_text(
                width / 2,
                height / 2,
                text="Gas resistance stream\n(waiting for data)",
                fill="#666666",
                justify="center",
                font=("TkDefaultFont", 9),
            )
        else:
            self.graph_placeholder = None

    def _schedule_graph_redraw(self) -> None:
        if not hasattr(self, "graph_canvas"):
            return
        if self.graph_redraw_pending:
            return
        self.graph_redraw_pending = True
        self.root.after(0, self._redraw_graph)

    def _append_graph_point(self, gas_value: float) -> None:
        if math.isnan(gas_value):
            return
        timestamp = time.monotonic()
        cutoff = timestamp - self.graph_window_seconds
        self.graph_data.append((timestamp, gas_value))
        while self.graph_data and self.graph_data[0][0] < cutoff:
            self.graph_data.popleft()
        if hasattr(self, "graph_canvas") and self.graph_placeholder is not None:
            self.graph_canvas.delete(self.graph_placeholder)
            self.graph_placeholder = None
        self._schedule_graph_redraw()

    def _redraw_graph(self) -> None:
        self.graph_redraw_pending = False
        if not hasattr(self, "graph_canvas"):
            return
        canvas = self.graph_canvas
        width = max(int(canvas.winfo_width()), 2)
        height = max(int(canvas.winfo_height()), 2)
        canvas.delete("all")
        self.graph_placeholder = None
        if not self.graph_data:
            self.graph_placeholder = canvas.create_text(
                width / 2,
                height / 2,
                text="Gas resistance stream\n(waiting for data)",
                fill="#666666",
                justify="center",
                font=("TkDefaultFont", 9),
            )
            return

        last_time = self.graph_data[-1][0]
        first_time = self.graph_data[0][0]
        span = max(last_time - first_time, 0.0)
        window = self.graph_window_seconds if span >= self.graph_window_seconds else max(span, 1.0)
        start = last_time - window

        values = [value for _, value in self.graph_data if value is not None and math.isfinite(value)]
        if not values:
            self.graph_placeholder = canvas.create_text(
                width / 2,
                height / 2,
                text="Gas resistance stream\n(waiting for data)",
                fill="#666666",
                justify="center",
                font=("TkDefaultFont", 9),
            )
            return
        min_val = min(values)
        max_val = max(values)
        if math.isclose(min_val, max_val):
            offset = max(abs(max_val) * 0.05, 1.0)
            min_val -= offset
            max_val += offset

        pad_x = 40
        pad_y = 16
        usable_width = max(width - 2 * pad_x, 10)
        usable_height = max(height - 2 * pad_y, 10)
        rect_x0 = pad_x
        rect_y0 = pad_y
        rect_x1 = pad_x + usable_width
        rect_y1 = pad_y + usable_height
        canvas.create_rectangle(rect_x0, rect_y0, rect_x1, rect_y1, outline="#cbd5f5", fill="#f8fafc")

        for fraction in (0.25, 0.5, 0.75):
            y = rect_y0 + fraction * usable_height
            canvas.create_line(rect_x0, y, rect_x1, y, fill="#e2e8f0", dash=(2, 4))

        time_ticks = [0, window / 4, window / 2, 3 * window / 4, window]
        for tick in time_ticks:
            x = rect_x0 + (tick / window) * usable_width
            canvas.create_line(x, rect_y0, x, rect_y1, fill="#edf2fa")

        coords: List[float] = []
        for timestamp, value in self.graph_data:
            if timestamp < start:
                continue
            x_frac = (timestamp - start) / window if window > 0 else 0.0
            x = rect_x0 + x_frac * usable_width
            y_frac = (value - min_val) / (max_val - min_val) if max_val != min_val else 0.5
            y = rect_y1 - y_frac * usable_height
            coords.extend([x, y])
        if len(coords) >= 4:
            canvas.create_line(*coords, fill="#2563eb", width=2, smooth=True)

        current_value = self.graph_data[-1][1]
        canvas.create_text(
            rect_x1,
            rect_y0 - 6,
            anchor="ne",
            text=f"Current: {self._format_gas_value(current_value)}",
            fill="#1e3a8a",
            font=("TkDefaultFont", 9, "bold"),
        )
        canvas.create_text(
            rect_x0,
            rect_y0 - 6,
            anchor="nw",
            text=f"Range: {self._format_gas_value(min_val)} to {self._format_gas_value(max_val)}",
            fill="#334155",
            font=("TkDefaultFont", 8),
        )
        canvas.create_text(
            rect_x0,
            rect_y1 + 6,
            anchor="nw",
            text=self._format_window_label(window),
            fill="#475569",
            font=("TkDefaultFont", 8),
        )

    def _initialize_progress(self, profile: Profile, cycles_target: int, skip_cycles: int) -> None:
        self._reset_progress()
        durations = [float(max(0, step.duration_ms)) for step in profile.steps]
        prefix: List[float] = [0.0]
        total = 0.0
        for duration in durations:
            total += duration
            prefix.append(total)
        if total <= 0.0:
            total = 1.0
            prefix = [0.0, total]
        total_cycles = max(0, skip_cycles) + max(0, cycles_target)
        warmup_ms = float(CollectorRunner.WARMUP_SECONDS * 1000)
        total_ms = warmup_ms + total_cycles * total
        if total_ms <= 0.0:
            total_ms = 1.0
        self.progress_cycle_prefix = prefix
        self.progress_cycle_total_ms = total
        self.progress_warmup_ms = warmup_ms
        self.progress_total_ms = total_ms
        self.progress_inferred_ms = 0.0
        self.progress_start_time = time.monotonic()
        self.progress_active = True
        self._update_progress_time(force=True)

    def _update_progress_from_step(self, cycle_index: int, step_index: int) -> None:
        if not self.progress_active:
            return
        steps_in_cycle = len(self.progress_cycle_prefix) - 1
        if steps_in_cycle <= 0:
            return
        safe_cycle = max(int(cycle_index), 0)
        safe_step_index = max(int(step_index), 0)
        step_pos = min(safe_step_index, len(self.progress_cycle_prefix) - 1)
        cycle_contrib = float(safe_cycle) * self.progress_cycle_total_ms
        step_contrib = self.progress_cycle_prefix[step_pos]
        inferred = self.progress_warmup_ms + cycle_contrib + step_contrib
        self.progress_inferred_ms = max(self.progress_inferred_ms, inferred)
        self._update_progress_time()

    def _update_progress_time(self, force: bool = False) -> None:
        if not self.progress_active and not force:
            return
        total_ms = max(self.progress_total_ms, 1.0)
        progress_ms = min(self.progress_inferred_ms, total_ms)
        if self.progress_start_time is not None:
            elapsed_ms = max((time.monotonic() - self.progress_start_time) * 1000.0, 0.0)
            warmup_progress = min(elapsed_ms, self.progress_warmup_ms)
            progress_ms = max(progress_ms, warmup_progress)
        progress_ms = min(progress_ms, total_ms)
        self.progress_var.set(progress_ms / total_ms)
        remaining_ms = max(total_ms - progress_ms, 0.0)
        if not self.progress_active and remaining_ms <= 0.0:
            eta_text = "ETA: 0s"
        else:
            eta_text = f"ETA: {self._format_eta(remaining_ms)}"
        self.label_eta.configure(text=eta_text)

    def _format_eta(self, remaining_ms: float) -> str:
        remaining_seconds = remaining_ms / 1000.0
        if remaining_seconds >= 3600:
            hours = int(remaining_seconds // 3600)
            minutes = int((remaining_seconds % 3600) // 60)
            return f"{hours}h {minutes:02d}m"
        if remaining_seconds >= 60:
            minutes = int(remaining_seconds // 60)
            seconds = int(remaining_seconds % 60)
            return f"{minutes}m {seconds:02d}s"
        if remaining_seconds >= 10:
            return f"{int(round(remaining_seconds))}s"
        if remaining_seconds > 0:
            return f"{remaining_seconds:.1f}s"
        return "0s"

    def _format_gas_value(self, value: float) -> str:
        magnitude = abs(value)
        if magnitude >= 1_000_000:
            return f"{value / 1_000_000:.2f} Mohm"
        if magnitude >= 1_000:
            return f"{value / 1_000:.2f} kohm"
        if magnitude >= 1:
            return f"{value:.2f} ohm"
        return f"{value:.3f} ohm"

    def _format_window_label(self, seconds: float) -> str:
        if seconds >= self.graph_window_seconds - 0.5:
            return "Past 2 min"
        if seconds >= 60:
            return f"Past {seconds / 60:.1f} min"
        return f"Past {max(seconds, 1):.0f}s"

    def _finalize_progress(self, success: bool) -> None:
        if success:
            self.progress_inferred_ms = self.progress_total_ms
            self.progress_active = False
            self._update_progress_time(force=True)
        else:
            self._reset_progress()
        self.progress_start_time = None

    def _drain_status_queue(self) -> None:
        try:
            while True:
                self.status_queue.get_nowait()
        except queue.Empty:
            pass

    def _poll_status_queue(self) -> None:
        try:
            while True:
                payload = self.status_queue.get_nowait()
                if "__complete__" in payload:
                    path = payload["__complete__"]
                    self._finalize_progress(True)
                    if path:
                        messagebox.showinfo("Run complete", f"Data saved to {path}")
                    self.btn_start.configure(state="normal")
                    self.btn_stop.configure(state="disabled")
                    self.runner_thread = None
                    self.runner = None
                elif "__error__" in payload:
                    self._finalize_progress(False)
                    messagebox.showerror("Run failed", payload["__error__"])
                    self.btn_start.configure(state="normal")
                    self.btn_stop.configure(state="disabled")
                    self.runner_thread = None
                    self.runner = None
                else:
                    self._update_status(payload)
        except queue.Empty:
            pass
        self._update_progress_time()
        self.root.after(200, self._poll_status_queue)

    def _update_status(self, row: Dict[str, object]) -> None:
        def as_float(value: object) -> float:
            if isinstance(value, (int, float)):
                return float(value)
            try:
                return float(value)
            except Exception:
                return float("nan")

        def as_int(value: object) -> int:
            if isinstance(value, int):
                return value
            try:
                return int(float(value))
            except Exception:
                return 0

        cycle = as_int(row.get("cycle_index"))
        warmup = bool(row.get("warmup_cycle"))
        step = as_int(row.get("step_index"))
        heater_temp = as_float(row.get("commanded_heater_temp_C"))
        ticks = as_int(row.get("step_duration_ticks"))
        step_ms = as_float(row.get("step_duration_ms"))

        cycle_label = f"Cycle: {cycle + 1 if cycle >= 0 else cycle}"
        if warmup:
            cycle_label += " (warmup)"
        self.label_cycle.configure(text=cycle_label)
        self.label_step.configure(text=f"Step: {step}")
        if math.isnan(heater_temp):
            self.label_command.configure(text="Heater: -")
        else:
            self.label_command.configure(
                text=f"Heater: {heater_temp:.0f} deg C / {ticks} ticks (~{step_ms:.0f} ms)"
            )

        gas = as_float(row.get("gas_resistance_ohm"))
        self.label_gas.configure(text=f"Gas: {gas:.2f}" if not math.isnan(gas) else "Gas: -")
        temp = as_float(row.get("sensor_temperature_C"))
        self.label_temp.configure(text=f"Temp: {temp:.2f} °C" if not math.isnan(temp) else "Temp: -")
        humidity = as_float(row.get("sensor_humidity_RH"))
        self.label_humidity.configure(
            text=f"Humidity: {humidity:.2f} %" if not math.isnan(humidity) else "Humidity: -"
        )
        pressure = as_float(row.get("pressure_Pa"))
        self.label_pressure.configure(
            text=f"Pressure: {pressure:.2f} Pa" if not math.isnan(pressure) else "Pressure: -"
        )
        if not math.isnan(gas):
            self._append_graph_point(gas)
        self._update_progress_from_step(cycle, step)

    def run(self) -> None:
        self.root.mainloop()
