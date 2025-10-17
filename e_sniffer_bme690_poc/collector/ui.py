from __future__ import annotations
import math
import time
import queue
import threading
import tkinter as tk
from collections import deque
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Callable, Deque, Dict, Iterable, List, Optional, Set
from .label_store import AttributeDefinition, AttributeOption, ClassTemplate, LabelStore
from .profiles import Profile, ProfileStep, profile_from_default
from .runtime import CollectorRunner, Metadata, RunConfig, build_backend
TICK_DURATION_MS = 140
STORAGE_OPTIONS = ["refrigerated", "countertop", "frozen", "other"]
ATTRIBUTE_ROLE_CHOICES: List[tuple[Optional[str], str]] = [
    ("label", "Label component (primary)"),
    (None, "Label component"),
]
ATTRIBUTE_INPUT_TYPES: List[tuple[str, str]] = [
    ("list", "List of choices"),
    ("number", "Numeric entry"),
]
def attribute_role_display(role: Optional[str]) -> str:
    for value, label in ATTRIBUTE_ROLE_CHOICES:
        if value == role:
            return label
    return "Label component"
def attribute_input_display(input_type: str) -> str:
    for value, label in ATTRIBUTE_INPUT_TYPES:
        if value == input_type:
            return label
    return "List of choices"
def attribute_input_internal(label: str) -> str:
    for value, display in ATTRIBUTE_INPUT_TYPES:
        if display == label:
            return value
    return "list"
class OptionEditor(tk.Toplevel):
    def __init__(
        self,
        master: tk.Misc,
        option: Optional[AttributeOption],
        dependencies: Dict[str, AttributeDefinition],
    ) -> None:
        super().__init__(master)
        self.title("Attribute option")
        self.geometry("660x520")
        self.minsize(560, 440)
        self.resizable(True, True)
        self.result: Optional[AttributeOption] = None
        self.dependencies = dependencies
        self.var_value = tk.StringVar(value=option.value if option else "")
        self.parent_lists: Dict[str, tk.Listbox] = {}
        container = ttk.Frame(self, padding=12)
        container.grid(row=0, column=0, sticky="nsew")
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        ttk.Label(container, text="Option value").grid(row=0, column=0, sticky="w")
        ttk.Entry(container, textvariable=self.var_value, width=40).grid(row=0, column=1, sticky="ew")
        row = 1
        option_constraints = option.parent_constraints if option else {}
        for parent_name, definition in dependencies.items():
            lf = ttk.LabelFrame(container, text=f"Allowed with {parent_name}", padding=6)
            lf.grid(row=row, column=0, columnspan=2, pady=(8 if row == 1 else 4, 0), sticky="ew")
            row += 1
            listbox = tk.Listbox(lf, selectmode="multiple", height=min(len(definition.options), 6), exportselection=False)
            listbox.grid(row=0, column=0, sticky="nsew")
            lf.columnconfigure(0, weight=1)
            lf.rowconfigure(0, weight=1)
            for idx, parent_option in enumerate(definition.options):
                listbox.insert("end", parent_option.value)
                selected_values = option_constraints.get(parent_name, [])
                if parent_option.value in selected_values:
                    listbox.selection_set(idx)
            self.parent_lists[parent_name] = listbox
        if not dependencies:
            ttk.Label(container, text="No parent requirements (available for all selections)").grid(
                row=row, column=0, columnspan=2, pady=(8, 0), sticky="w"
            )
        button_frame = ttk.Frame(container)
        button_frame.grid(row=row + 1, column=0, columnspan=2, pady=(12, 0))
        ttk.Button(button_frame, text="Cancel", command=self.destroy).grid(row=0, column=0, padx=6)
        ttk.Button(button_frame, text="Save", command=self._on_save).grid(row=0, column=1, padx=6)
        container.columnconfigure(1, weight=1)
        self.grab_set()
        self.transient(master)
        self.var_value.trace_add("write", lambda *_: None)
    def _on_save(self) -> None:
        value = self.var_value.get().strip()
        if not value:
            messagebox.showerror("Invalid value", "Option value cannot be empty.", parent=self)
            return
        constraints: Dict[str, List[str]] = {}
        for parent_name, listbox in self.parent_lists.items():
            selections = [listbox.get(idx) for idx in listbox.curselection()]
            if selections:
                constraints[parent_name] = selections
        self.result = AttributeOption(value=value, parent_constraints=constraints)
        self.destroy()
class AttributeEditor(tk.Toplevel):
    def __init__(
        self,
        master: tk.Misc,
        attribute: Optional[AttributeDefinition],
        parent_attributes: Dict[str, AttributeDefinition],
    ) -> None:
        super().__init__(master)
        self.title("Attribute definition")
        self.geometry("720x560")
        self.minsize(620, 500)
        self.resizable(True, True)
        self.result: Optional[AttributeDefinition] = None
        self.parent_attributes = parent_attributes
        self.var_name = tk.StringVar(value=attribute.name if attribute else "")
        self.var_role = tk.StringVar()
        self.var_input_type = tk.StringVar()
        default_role = attribute.role if attribute else None
        self.var_role.set("" if default_role is None else default_role)
        default_input_type = (attribute.input_type if attribute else "list") if attribute else "list"
        self.var_input_type.set(attribute_input_display(default_input_type))
        self.dependencies_list: Optional[tk.Listbox] = None
        self.tree_options: Optional[ttk.Treeview] = None
        self.options: List[AttributeOption] = [option for option in (attribute.options if attribute else [])]
        self.scroll_options: Optional[ttk.Scrollbar] = None
        self.buttons_options: Optional[ttk.Frame] = None
        container = ttk.Frame(self, padding=12)
        container.grid(row=0, column=0, sticky="nsew")
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        ttk.Label(container, text="Attribute name").grid(row=0, column=0, sticky="w")
        ttk.Entry(container, textvariable=self.var_name, width=32).grid(row=0, column=1, sticky="ew")
        ttk.Label(container, text="Role (label emphasis)").grid(row=1, column=0, sticky="w")
        role_combo = ttk.Combobox(
            container,
            textvariable=self.var_role,
            state="readonly",
            values=[label for _, label in ATTRIBUTE_ROLE_CHOICES],
        )
        role_combo.grid(row=1, column=1, sticky="ew")
        role_combo.set(attribute_role_display(default_role))
        ttk.Label(container, text="Value type").grid(row=2, column=0, sticky="w")
        value_type_combo = ttk.Combobox(
            container,
            textvariable=self.var_input_type,
            state="readonly",
            values=[label for _, label in ATTRIBUTE_INPUT_TYPES],
        )
        value_type_combo.grid(row=2, column=1, sticky="ew")
        value_type_combo.set(self.var_input_type.get())
        value_type_combo.bind("<<ComboboxSelected>>", lambda *_: self._update_value_type_state())
        ttk.Label(container, text="Depends on").grid(row=3, column=0, sticky="nw")
        self.dependencies_list = tk.Listbox(container, selectmode="multiple", height=6, exportselection=False)
        self.dependencies_list.grid(row=3, column=1, sticky="ew")
        available_names = list(parent_attributes.keys())
        for idx, name in enumerate(available_names):
            self.dependencies_list.insert("end", name)
        if attribute:
            for idx, name in enumerate(available_names):
                if name in attribute.dependencies:
                    self.dependencies_list.selection_set(idx)
        ttk.Label(
            container,
            text="Select parent attributes this field depends on. Parent attributes must already exist in the list.",
            wraplength=320,
            justify="left",
            foreground="#475569",
        ).grid(row=4, column=0, columnspan=2, sticky="w", pady=(4, 0))
        options_frame = ttk.LabelFrame(container, text="Options for this attribute", padding=6)
        options_frame.grid(row=5, column=0, columnspan=2, pady=(10, 0), sticky="nsew")
        options_frame.columnconfigure(0, weight=1)
        options_frame.rowconfigure(0, weight=1)
        self.tree_options = ttk.Treeview(
            options_frame,
            columns=("value", "constraints"),
            show="headings",
            height=6,
            selectmode="browse",
        )
        self.tree_options.heading("value", text="Option value")
        self.tree_options.heading("constraints", text="Parent requirements")
        self.tree_options.column("value", anchor="w", width=200, stretch=True)
        self.tree_options.column("constraints", anchor="w", width=280, stretch=True)
        self.tree_options.grid(row=0, column=0, sticky="nsew")
        self.scroll_options = ttk.Scrollbar(options_frame, orient="vertical", command=self.tree_options.yview)
        self.tree_options.configure(yscrollcommand=self.scroll_options.set)
        self.scroll_options.grid(row=0, column=1, sticky="ns")
        self.buttons_options = ttk.Frame(options_frame)
        self.buttons_options.grid(row=1, column=0, columnspan=2, pady=(6, 0), sticky="ew")
        for idx in range(3):
            self.buttons_options.columnconfigure(idx, weight=1)
        ttk.Button(self.buttons_options, text="Add option", command=self._add_option).grid(row=0, column=0, padx=4, pady=2, sticky="ew")
        ttk.Button(self.buttons_options, text="Edit option", command=self._edit_option).grid(row=0, column=1, padx=4, pady=2, sticky="ew")
        ttk.Button(self.buttons_options, text="Remove option", command=self._remove_option).grid(row=0, column=2, padx=4, pady=2, sticky="ew")
        self.label_numeric_hint = ttk.Label(
            options_frame,
            text="Numeric attributes do not use preset options. Operators will enter a value during collection.",
            foreground="#475569",
            wraplength=360,
            justify="left",
        )
        self.label_numeric_hint.grid(row=0, column=0, columnspan=2, sticky="nsew", pady=8)
        self.label_numeric_hint.grid_remove()
        action = ttk.Frame(container)
        action.grid(row=6, column=0, columnspan=2, pady=(12, 0))
        ttk.Button(action, text="Cancel", command=self.destroy).grid(row=0, column=0, padx=6)
        ttk.Button(action, text="Save", command=self._on_save).grid(row=0, column=1, padx=6)
        container.columnconfigure(1, weight=1)
        container.rowconfigure(5, weight=1)
        self._update_value_type_state()
        self._refresh_options()
        self.grab_set()
        self.transient(master)
    def _value_type(self) -> str:
        return attribute_input_internal(self.var_input_type.get())
    def _update_value_type_state(self) -> None:
        value_type = self._value_type()
        if value_type == "list":
            if self.label_numeric_hint:
                self.label_numeric_hint.grid_remove()
            if self.tree_options:
                self.tree_options.grid(row=0, column=0, sticky="nsew")
            if self.scroll_options:
                self.scroll_options.grid(row=0, column=1, sticky="ns")
            if self.buttons_options:
                self.buttons_options.grid(row=1, column=0, columnspan=2, pady=(6, 0), sticky="ew")
        else:
            if self.tree_options:
                self.tree_options.grid_remove()
            if self.scroll_options:
                self.scroll_options.grid_remove()
            if self.buttons_options:
                self.buttons_options.grid_remove()
            if self.label_numeric_hint:
                self.label_numeric_hint.grid(row=0, column=0, columnspan=2, sticky="nsew", pady=8)
        if value_type == "list":
            self._refresh_options()
    def _selected_dependencies(self) -> List[str]:
        if not self.dependencies_list:
            return []
        return [self.dependencies_list.get(idx) for idx in self.dependencies_list.curselection()]
    def _refresh_options(self) -> None:
        if not self.tree_options:
            return
        if self._value_type() != "list":
            return
        for row in self.tree_options.get_children():
            self.tree_options.delete(row)
        dependencies = self._selected_dependencies()
        for idx, option in enumerate(self.options):
            parts = []
            for parent_name in dependencies:
                allowed = option.parent_constraints.get(parent_name)
                if not allowed:
                    continue
                parts.append(f"{parent_name}: {', '.join(allowed)}")
            summary = "; ".join(parts) if parts else "Available for all parent selections"
            self.tree_options.insert("", "end", iid=str(idx), values=(option.value, summary))
    def _add_option(self) -> None:
        if self._value_type() != "list":
            return
        dependencies = {name: self.parent_attributes[name] for name in self._selected_dependencies()}
        dialog = OptionEditor(self, None, dependencies)
        self.wait_window(dialog)
        if dialog.result:
            self.options.append(dialog.result)
            self._refresh_options()
    def _edit_option(self) -> None:
        if self._value_type() != "list":
            return
        if not self.tree_options:
            return
        selection = self.tree_options.selection()
        if not selection:
            return
        index = int(selection[0])
        dependencies = {name: self.parent_attributes[name] for name in self._selected_dependencies()}
        dialog = OptionEditor(self, self.options[index], dependencies)
        self.wait_window(dialog)
        if dialog.result:
            self.options[index] = dialog.result
            self._refresh_options()
    def _remove_option(self) -> None:
        if self._value_type() != "list":
            return
        if not self.tree_options:
            return
        selection = self.tree_options.selection()
        if not selection:
            return
        index = int(selection[0])
        del self.options[index]
        self._refresh_options()
    def _resolve_role(self) -> Optional[str]:
        display = self.var_role.get()
        for value, label in ATTRIBUTE_ROLE_CHOICES:
            if label == display:
                return value
        return None
    def _on_save(self) -> None:
        name = self.var_name.get().strip()
        if not name:
            messagebox.showerror("Invalid attribute", "Attribute name is required.", parent=self)
            return
        value_type = self._value_type()
        if value_type == "list" and not self.options:
            messagebox.showerror("Invalid attribute", "At least one option is required.", parent=self)
            return
        dependencies = self._selected_dependencies()
        missing_parents = [parent for parent in dependencies if parent not in self.parent_attributes]
        if missing_parents:
            messagebox.showerror("Invalid dependency", f"Unknown dependency: {', '.join(missing_parents)}", parent=self)
            return
        role_value = self._resolve_role()
        definition = AttributeDefinition(
            name=name,
            role=role_value,
            dependencies=dependencies,
            options=[option for option in self.options] if value_type == "list" else [],
            input_type=value_type,
        )
        self.result = definition
        self.destroy()
class ClassTemplateEditor(tk.Toplevel):
    def __init__(
        self,
        master: tk.Misc,
        template: Optional[ClassTemplate],
        existing_names: List[str],
    ) -> None:
        super().__init__(master)
        self.title("Label category template")
        self.geometry("860x640")
        self.minsize(720, 560)
        self.resizable(True, True)
        self.result: Optional[ClassTemplate] = None
        self.original_name = template.name if template else None
        self.existing_names = set(existing_names)
        if self.original_name:
            self.existing_names.discard(self.original_name)
        self.template = template.copy() if template else ClassTemplate(name="")
        self.var_name = tk.StringVar(value=self.template.name)
        self.tree_attributes: Optional[ttk.Treeview] = None
        container = ttk.Frame(self, padding=12)
        container.grid(row=0, column=0, sticky="nsew")
        ttk.Label(container, text="Category name").grid(row=0, column=0, sticky="w")
        ttk.Entry(container, textvariable=self.var_name, width=40).grid(row=0, column=1, sticky="ew")
        guidance = (
            "Tip: build your category from the top of the tree downward.\n"
            "Add the broadest attribute first (for example Protein Type), then add child attributes\n"
            "that depend on it (such as Cut or Feed). Select parent attributes in the \"Depends on\" list\n"
            "while editing each child. You can reopen an attribute later if you need to change its parent links."
        )
        ttk.Label(container, text=guidance, wraplength=420, justify="left", foreground="#475569").grid(
            row=1, column=0, columnspan=2, sticky="w", pady=(6, 0)
        )
        attributes_frame = ttk.LabelFrame(container, text="Attributes / tree levels", padding=6)
        attributes_frame.grid(row=2, column=0, columnspan=2, pady=(10, 0), sticky="nsew")
        attributes_frame.columnconfigure(0, weight=1)
        attributes_frame.rowconfigure(0, weight=1)
        self.tree_attributes = ttk.Treeview(
            attributes_frame,
            columns=("attribute", "role", "dependencies", "options"),
            show="headings",
            height=8,
            selectmode="browse",
        )
        self.tree_attributes.heading("attribute", text="Attribute")
        self.tree_attributes.heading("role", text="Role")
        self.tree_attributes.heading("dependencies", text="Depends on")
        self.tree_attributes.heading("options", text="Options")
        self.tree_attributes.column("attribute", width=200, anchor="w")
        self.tree_attributes.column("role", width=180, anchor="w")
        self.tree_attributes.column("dependencies", width=240, anchor="w")
        self.tree_attributes.column("options", width=80, anchor="center")
        self.tree_attributes.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(attributes_frame, orient="vertical", command=self.tree_attributes.yview)
        self.tree_attributes.configure(yscrollcommand=scrollbar.set)
        scrollbar.grid(row=0, column=1, sticky="ns")
        buttons = ttk.Frame(attributes_frame)
        buttons.grid(row=1, column=0, columnspan=2, pady=(6, 0))
        ttk.Button(buttons, text="Add attribute", command=self._add_attribute).grid(row=0, column=0, padx=4)
        ttk.Button(buttons, text="Edit attribute", command=self._edit_attribute).grid(row=0, column=1, padx=4)
        ttk.Button(buttons, text="Remove attribute", command=self._remove_attribute).grid(row=0, column=2, padx=4)
        ttk.Button(buttons, text="Move up", command=lambda: self._move_attribute(-1)).grid(row=0, column=3, padx=4)
        ttk.Button(buttons, text="Move down", command=lambda: self._move_attribute(1)).grid(row=0, column=4, padx=4)
        action = ttk.Frame(container)
        action.grid(row=3, column=0, columnspan=2, pady=(12, 0))
        ttk.Button(action, text="Cancel", command=self.destroy).grid(row=0, column=0, padx=6)
        ttk.Button(action, text="Save", command=self._on_save).grid(row=0, column=1, padx=6)
        container.columnconfigure(1, weight=1)
        container.rowconfigure(2, weight=1)
        self._refresh_attributes()
        self.grab_set()
        self.transient(master)
    def _refresh_attributes(self) -> None:
        if not self.tree_attributes:
            return
        for row in self.tree_attributes.get_children():
            self.tree_attributes.delete(row)
        for idx, attribute in enumerate(self.template.attributes):
            dependencies = ", ".join(attribute.dependencies) if attribute.dependencies else "-"
            self.tree_attributes.insert(
                "",
                "end",
                iid=str(idx),
                values=(
                    attribute.name,
                    attribute_role_display(attribute.role),
                    dependencies if dependencies else "-",
                    "Numeric entry" if attribute.input_type == "number" else f"{len(attribute.options)} option{'s' if len(attribute.options) != 1 else ''}",
                ),
            )
    def _parent_map(self, exclude: Optional[str] = None) -> Dict[str, AttributeDefinition]:
        mapping: Dict[str, AttributeDefinition] = {}
        for attribute in self.template.attributes:
            if attribute.name == exclude:
                continue
            mapping[attribute.name] = attribute
        return mapping
    def _selected_index(self) -> Optional[int]:
        if not self.tree_attributes:
            return None
        selection = self.tree_attributes.selection()
        if not selection:
            return None
        return int(selection[0])
    def _add_attribute(self) -> None:
        dialog = AttributeEditor(self, None, self._parent_map())
        self.wait_window(dialog)
        if dialog.result:
            if any(existing.name == dialog.result.name for existing in self.template.attributes):
                messagebox.showerror(
                    "Duplicate attribute",
                    f"Attribute '{dialog.result.name}' already exists.",
                    parent=self,
                )
                return
            self.template.attributes.append(dialog.result)
            self._refresh_attributes()
    def _edit_attribute(self) -> None:
        index = self._selected_index()
        if index is None:
            return
        target = self.template.attributes[index]
        dialog = AttributeEditor(self, target, self._parent_map(exclude=target.name))
        self.wait_window(dialog)
        if dialog.result:
            if dialog.result.name != target.name and any(
                existing.name == dialog.result.name for existing in self.template.attributes
            ):
                messagebox.showerror(
                    "Duplicate attribute",
                    f"Attribute '{dialog.result.name}' already exists.",
                    parent=self,
                )
                return
            self.template.attributes[index] = dialog.result
            self._refresh_attributes()
    def _remove_attribute(self) -> None:
        index = self._selected_index()
        if index is None:
            return
        target = self.template.attributes[index]
        dependent = [
            attribute.name
            for attribute in self.template.attributes
            if target.name in attribute.dependencies
        ]
        if dependent:
            messagebox.showerror(
                "Cannot remove",
                f"Attribute '{target.name}' is required by: {', '.join(dependent)}.",
                parent=self,
            )
            return
        if messagebox.askyesno("Remove attribute", f"Remove '{target.name}'?", parent=self):
            del self.template.attributes[index]
            self._refresh_attributes()
    def _move_attribute(self, delta: int) -> None:
        index = self._selected_index()
        if index is None:
            return
        target_index = index + delta
        if not (0 <= target_index < len(self.template.attributes)):
            return
        moving = self.template.attributes[index]
        if delta < 0:
            # moving up, ensure dependencies remain before
            for dependency in moving.dependencies:
                dep_index = next(
                    (i for i, attr in enumerate(self.template.attributes) if attr.name == dependency),
                    None,
                )
                if dep_index is not None and dep_index >= target_index:
                    messagebox.showerror(
                        "Cannot reorder",
                        f"'{moving.name}' depends on '{dependency}' which must remain before it.",
                        parent=self,
                    )
                    return
        elif delta > 0:
            # moving down, ensure dependents stay after
            dependents = [
                attr.name
                for attr in self.template.attributes
                if moving.name in attr.dependencies
            ]
            for dependent_name in dependents:
                dep_index = next(
                    (i for i, attr in enumerate(self.template.attributes) if attr.name == dependent_name),
                    None,
                )
                if dep_index is not None and dep_index <= target_index:
                    messagebox.showerror(
                        "Cannot reorder",
                        f"'{moving.name}' must stay before dependent '{dependent_name}'.",
                        parent=self,
                    )
                    return
        self.template.attributes[index], self.template.attributes[target_index] = (
            self.template.attributes[target_index],
            self.template.attributes[index],
        )
        self._refresh_attributes()
        if self.tree_attributes:
            self.tree_attributes.selection_set(str(target_index))
    def _on_save(self) -> None:
        name = self.var_name.get().strip()
        if not name:
            messagebox.showerror("Invalid template", "Category name is required.", parent=self)
            return
        if name in self.existing_names:
            messagebox.showerror(
                "Duplicate category",
                f"A category named '{name}' already exists.",
                parent=self,
            )
            return
        if not self.template.attributes:
            messagebox.showerror(
                "Invalid template",
                "Add at least one attribute to the category.",
                parent=self,
            )
            return
        self.template.name = name
        self.result = self.template
        self.destroy()
class LabelManagerDialog(tk.Toplevel):
    def __init__(self, master: tk.Misc, store: LabelStore) -> None:
        super().__init__(master)
        self.title("Manage label categories")
        self.geometry("840x640")
        self.minsize(720, 540)
        self.resizable(True, True)
        self.store = store.copy()
        self.result: Optional[LabelStore] = None
        self.current_primary_value: Optional[str] = None
        container = ttk.Frame(self, padding=12)
        container.grid(row=0, column=0, sticky="nsew")
        container.columnconfigure(0, weight=1)
        container.columnconfigure(1, weight=2)
        container.rowconfigure(1, weight=1)
        ttk.Label(container, text="Categories").grid(row=0, column=0, sticky="w")
        ttk.Label(container, text="Details").grid(row=0, column=1, sticky="w")
        categories_frame = ttk.Frame(container)
        categories_frame.grid(row=1, column=0, sticky="nsew", padx=(0, 12))
        categories_frame.columnconfigure(0, weight=1)
        categories_frame.rowconfigure(0, weight=1)
        self.tree_classes = ttk.Treeview(
            categories_frame,
            columns=("fields",),
            show="tree headings",
            height=12,
            selectmode="browse",
        )
        self.tree_classes.heading("#0", text="Category")
        self.tree_classes.heading("fields", text="Fields")
        self.tree_classes.column("#0", anchor="w", width=260, stretch=True)
        self.tree_classes.column("fields", anchor="center", width=160, stretch=False)
        self.tree_classes.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(categories_frame, orient="vertical", command=self.tree_classes.yview)
        self.tree_classes.configure(yscrollcommand=scrollbar.set)
        scrollbar.grid(row=0, column=1, sticky="ns")
        detail_frame = ttk.Frame(container)
        detail_frame.grid(row=1, column=1, sticky="nsew")
        detail_frame.columnconfigure(0, weight=1)
        detail_frame.columnconfigure(1, weight=1)
        detail_frame.columnconfigure(2, weight=1)
        detail_frame.rowconfigure(1, weight=1)
        ttk.Label(detail_frame, text="Primary options").grid(row=0, column=0, sticky="w")
        ttk.Label(detail_frame, text="Attributes").grid(row=0, column=1, sticky="w")
        ttk.Label(detail_frame, text="Attribute options").grid(row=0, column=2, sticky="w")
        def _build_list(parent: ttk.Frame) -> tuple[ttk.Frame, tk.Listbox]:
            frame = ttk.Frame(parent)
            frame.columnconfigure(0, weight=1)
            frame.rowconfigure(0, weight=1)
            listbox = tk.Listbox(frame, height=10, exportselection=False)
            listbox.grid(row=0, column=0, sticky="nsew")
            scroll = ttk.Scrollbar(frame, orient="vertical", command=listbox.yview)
            scroll.grid(row=0, column=1, sticky="ns")
            listbox.configure(yscrollcommand=scroll.set)
            return frame, listbox
        primary_frame, self.list_primary = _build_list(detail_frame)
        primary_frame.grid(row=1, column=0, sticky="nsew", padx=(0, 8))
        attributes_frame, self.list_attributes = _build_list(detail_frame)
        attributes_frame.grid(row=1, column=1, sticky="nsew", padx=(0, 8))
        options_frame, self.list_options = _build_list(detail_frame)
        options_frame.grid(row=1, column=2, sticky="nsew")
        self.list_primary.bind("<<ListboxSelect>>", self._on_primary_select)
        self.list_attributes.bind("<<ListboxSelect>>", self._on_attribute_select)
        self.label_option_detail = ttk.Label(detail_frame, text="", wraplength=420, justify="left", foreground="#475569")
        self.label_option_detail.grid(row=2, column=0, columnspan=3, sticky="w", pady=(6, 0))
        ttk.Label(
            container,
            text=(
                "Each category can model a tree: add the broadest attribute first, then edit child attributes "
                "and mark their parent dependencies. Operators will only see attribute options that match their "
                "parent selections. Specimen ID and storage are entered on the Run Collection screen."
            ),
            wraplength=420,
            justify="left",
            foreground="#475569",
        ).grid(row=2, column=0, columnspan=2, sticky="w", pady=(8, 0))
        buttons = ttk.Frame(container)
        buttons.grid(row=3, column=0, columnspan=2, pady=(12, 0), sticky="ew")
        for idx in range(3):
            buttons.columnconfigure(idx, weight=1)
        ttk.Button(buttons, text="Add category", command=self._add_class).grid(row=0, column=0, padx=8, sticky="ew")
        ttk.Button(buttons, text="Edit category", command=self._edit_class).grid(row=0, column=1, padx=8, sticky="ew")
        ttk.Button(buttons, text="Remove category", command=self._remove_class).grid(row=0, column=2, padx=8, sticky="ew")
        footer = ttk.Frame(container)
        footer.grid(row=4, column=0, columnspan=2, pady=(16, 0), sticky="ew")
        footer.columnconfigure(0, weight=1)
        footer.columnconfigure(1, weight=1)
        ttk.Button(footer, text="Cancel", command=self.destroy).grid(row=0, column=0, padx=(0, 8), sticky="ew")
        ttk.Button(footer, text="Save changes", command=self._on_save).grid(row=0, column=1, padx=(8, 0), sticky="ew")
        self._refresh_classes()
        self.tree_classes.bind("<<TreeviewSelect>>", lambda _event: self._on_class_select())
        self.grab_set()
        self.transient(master)
    def _refresh_classes(self) -> None:
        for row in self.tree_classes.get_children():
            self.tree_classes.delete(row)
        for template in self.store.list_templates():
            field_count = len(template.attributes)
            self.tree_classes.insert(
                "",
                "end",
                iid=template.name,
                text=template.name,
                values=(f"{field_count} field{'s' if field_count != 1 else ''}",),
            )
        if self.tree_classes.get_children():
            current = self.tree_classes.selection()
            if not current:
                first = self.tree_classes.get_children()[0]
                self.tree_classes.selection_set(first)
                self.tree_classes.focus(first)
            self._on_class_select()
        else:
            self._clear_detail()
    def _selected_template(self) -> Optional[ClassTemplate]:
        selection = self.tree_classes.selection()
        if not selection:
            return None
        name = selection[0]
        return self.store.get_template(name)
    def _add_class(self) -> None:
        dialog = ClassTemplateEditor(self, None, [template.name for template in self.store.list_templates()])
        self.wait_window(dialog)
        if dialog.result:
            self.store.upsert_template(dialog.result)
            self._refresh_classes()
            self.tree_classes.selection_set(dialog.result.name)
            self.tree_classes.focus(dialog.result.name)
    def _edit_class(self) -> None:
        template = self._selected_template()
        if not template:
            return
        dialog = ClassTemplateEditor(
            self,
            template,
            [item.name for item in self.store.list_templates()],
        )
        self.wait_window(dialog)
        if dialog.result:
            if dialog.result.name != template.name:
                self.store.delete_template(template.name)
            self.store.upsert_template(dialog.result)
            self._refresh_classes()
            self.tree_classes.selection_set(dialog.result.name)
            self.tree_classes.focus(dialog.result.name)
    def _remove_class(self) -> None:
        template = self._selected_template()
        if not template:
            return
        if messagebox.askyesno(
            "Remove category",
            f"Delete category '{template.name}'?",
            parent=self,
        ):
            self.store.delete_template(template.name)
            self._refresh_classes()
            self._clear_detail()
    def _on_save(self) -> None:
        if not self.store.templates:
            messagebox.showerror(
                "No categories",
                "At least one category definition is required.",
                parent=self,
            )
            return
        self.result = self.store.copy()
        self.destroy()
    # ------------------------------------------------------------------ Detail helpers
    def _clear_detail(self) -> None:
        self.list_primary.delete(0, "end")
        self.list_attributes.delete(0, "end")
        self.list_options.delete(0, "end")
        self.label_option_detail.configure(text="")
        self.current_primary_value = None
    def _primary_attribute(self, template: ClassTemplate) -> Optional[AttributeDefinition]:
        for attribute in template.attributes:
            if attribute.role == "label":
                return attribute
        return template.attributes[0] if template.attributes else None
    def _on_class_select(self) -> None:
        template = self._selected_template()
        self.current_primary_value = None
        if not template:
            self._clear_detail()
            return
        primary = self._primary_attribute(template)
        self.list_primary.delete(0, "end")
        if primary:
            for option in primary.options:
                self.list_primary.insert("end", option.value)
            if primary.options:
                self.list_primary.selection_set(0)
                self.current_primary_value = primary.options[0].value
        self._populate_attributes(template, primary)
    def _populate_attributes(self, template: ClassTemplate, primary: Optional[AttributeDefinition]) -> None:
        self.list_attributes.delete(0, "end")
        for attribute in template.attributes:
            label = attribute.name
            if primary and attribute.name == primary.name:
                label += " (primary)"
            if attribute.input_type == "number":
                label += " (numeric entry)"
            self.list_attributes.insert("end", label)
        if template.attributes:
            selection_index = 0
            if primary and template.attributes[0].name == primary.name and len(template.attributes) > 1:
                selection_index = 1
            size = self.list_attributes.size()
            if size:
                if selection_index >= size:
                    selection_index = 0
                self.list_attributes.selection_set(selection_index)
        else:
            self.list_options.delete(0, "end")
            self.label_option_detail.configure(text="Select an attribute to view its options.")
            return
        self.label_option_detail.configure(text="Select an attribute to view its options.")
        self._on_attribute_select()
        self._on_attribute_select()
    def _on_primary_select(self, _event: Optional[tk.Event] = None) -> None:
        selection = self.list_primary.curselection()
        if selection:
            self.current_primary_value = self.list_primary.get(selection[0])
        else:
            self.current_primary_value = None
        template = self._selected_template()
        attribute_name = self._selected_attribute_name(template)
        if template and attribute_name:
            attribute = next((attr for attr in template.attributes if attr.name == attribute_name), None)
            self._populate_options(template, attribute)
    def _on_attribute_select(self, _event: Optional[tk.Event] = None) -> None:
        template = self._selected_template()
        attribute_name = self._selected_attribute_name(template)
        if not template or not attribute_name:
            self.list_options.delete(0, "end")
            self.label_option_detail.configure(text="")
            return
        attribute = next((attr for attr in template.attributes if attr.name == attribute_name), None)
        self._populate_options(template, attribute)
    def _selected_attribute_name(self, template: Optional[ClassTemplate]) -> Optional[str]:
        if not template:
            return None
        selection = self.list_attributes.curselection()
        if not selection:
            return None
        raw = self.list_attributes.get(selection[0])
        raw = raw.replace(" (primary)", "")
        raw = raw.replace(" (numeric entry)", "")
        return raw
    def _populate_options(self, template: ClassTemplate, attribute: Optional[AttributeDefinition]) -> None:
        self.list_options.delete(0, "end")
        if not attribute:
            self.label_option_detail.configure(text="Select an attribute to view its options.")
            return
        if attribute.input_type == "number":
            self.list_options.insert("end", "Numeric value entered during collection")
            detail_lines = [
                f"Attribute: {attribute.name}",
                f"Depends on: {', '.join(attribute.dependencies) if attribute.dependencies else 'No parent requirements'}",
                "Value type: Numeric entry",
            ]
            if primary and attribute.name == primary.name:
                detail_lines.append("This is the primary attribute (used as the sub-class).")
            elif has_primary_dependency and selected_primary:
                detail_lines.append(f"Linked to primary selection '{selected_primary}'.")
            self.label_option_detail.configure(text="\n".join(detail_lines))
            return
        primary = self._primary_attribute(template)
        primary_name = primary.name if primary else None
        selected_primary = self.current_primary_value
        has_primary_dependency = primary_name in attribute.dependencies if primary_name else False
        for option in attribute.options:
            parts: List[str] = [option.value]
            if option.parent_constraints:
                constraints = []
                for parent_name, allowed in option.parent_constraints.items():
                    constraints.append(f"{parent_name}: {', '.join(allowed)}")
                parts.append(f"[{'; '.join(constraints)}]")
            display = " ".join(parts)
            if selected_primary and has_primary_dependency:
                allowed = option.parent_constraints.get(primary_name, [])
                if allowed and selected_primary not in allowed:
                    display += "  (hidden for selected primary)"
            self.list_options.insert("end", display)
        detail_lines = [
            f"Attribute: {attribute.name}",
            f"Depends on: {', '.join(attribute.dependencies) if attribute.dependencies else 'No parent requirements'}",
            "Value type: List of choices",
        ]
        if primary and attribute.name == primary.name:
            detail_lines.append("This is the primary attribute (used as the sub-class).")
        elif has_primary_dependency and selected_primary:
            detail_lines.append(f"Showing options relevant to primary value '{selected_primary}'.")
        self.label_option_detail.configure(text="\n".join(detail_lines))
class ProfileEditorDialog(tk.Toplevel):
    def __init__(self, master: tk.Misc, profile: Profile) -> None:
        super().__init__(master)
        self.title("Edit Profile")
        self.geometry("620x520")
        self.minsize(520, 460)
        self.resizable(True, True)
        self.profile = profile.clone(name=profile.name, read_only=False)
        self.result: Optional[Profile] = None
        self.var_name = tk.StringVar(value=self.profile.name)
        self.var_backend = tk.StringVar(value=self.profile.backend)
        self.var_i2c = tk.StringVar(value=self.profile.i2c_addr)
        self.var_dwell = tk.StringVar(value=f"{self.profile.cycle_dwell_sec:.2f}")
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
        ttk.Label(container, text="Dwell between cycles (s)").grid(row=3, column=0, sticky="w")
        ttk.Entry(container, textvariable=self.var_dwell, width=10).grid(row=3, column=1, sticky="w")
        ttk.Label(container, text="Notes").grid(row=4, column=0, sticky="nw")
        notes_entry = ttk.Entry(container, textvariable=self.var_notes, width=40)
        notes_entry.grid(row=4, column=1, sticky="ew")
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
        self.tree.grid(row=5, column=0, columnspan=2, pady=8, sticky="nsew")
        button_frame = ttk.Frame(container)
        button_frame.grid(row=6, column=0, columnspan=2, pady=4)
        ttk.Button(button_frame, text="Add Step", command=self._add_step).grid(row=0, column=0, padx=4)
        ttk.Button(button_frame, text="Remove Step", command=self._remove_step).grid(row=0, column=1, padx=4)
        action_frame = ttk.Frame(container)
        action_frame.grid(row=7, column=0, columnspan=2, pady=(10, 0))
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
        dwell_text = self.var_dwell.get().strip()
        try:
            dwell_value = float(dwell_text) if dwell_text else 0.0
        except ValueError:
            messagebox.showerror("Validation error", "Dwell time must be numeric.", parent=self)
            return
        if dwell_value < 0:
            messagebox.showerror("Validation error", "Dwell time cannot be negative.", parent=self)
            return
        self.profile.cycle_dwell_sec = dwell_value
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
        self.geometry("420x260")
        self.minsize(360, 220)
        self.resizable(True, True)
        self.callback = callback
        self.var_temp = tk.IntVar(value=200)
        self.var_ticks = tk.IntVar(value=1)
        self.var_ms = tk.StringVar()
        frame = ttk.Frame(self, padding=10)
        frame.grid(row=0, column=0, sticky="nsew")
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
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
        self.root.geometry("1200x820")
        self.root.minsize(1000, 720)
        self.profiles: Dict[str, Profile] = {}
        self.active_profile_key: Optional[str] = None
        self.on_profile_selected = on_profile_selected
        self.label_store = LabelStore.load()
        self.var_label_template = tk.StringVar()
        self.var_specimen = tk.StringVar()
        self._specimen_manual = False
        self._updating_specimen = False
        self.entry_specimen: Optional[ttk.Entry] = None
        self.combo_storage: Optional[ttk.Combobox] = None
        self.attribute_vars: Dict[str, tk.StringVar] = {}
        self.attribute_widgets: Dict[str, tk.Widget] = {}
        self.attribute_dependents: Dict[str, Set[str]] = {}
        self.attribute_index: Dict[str, AttributeDefinition] = {}
        self.current_template: Optional[ClassTemplate] = None
        self.runner: Optional[CollectorRunner] = None
        self.runner_thread: Optional[threading.Thread] = None
        self.status_queue: "queue.Queue[dict]" = queue.Queue()
        self.progress_active = False
        self.progress_start_time: Optional[float] = None
        self.progress_total_ms: float = 1.0
        self.progress_cycle_total_ms: float = 0.0
        self.progress_cycle_prefix: List[float] = [0.0]
        self.progress_dwell_ms: float = 0.0
        self.progress_dwell_segments: int = 0
        self.progress_inferred_ms: float = 0.0
        self.progress_warmup_ms: float = 0.0
        self.graph_data: Deque[tuple[float, float]] = deque()
        self.graph_window_seconds = 120.0
        self.graph_redraw_pending = False
        self.graph_placeholder: Optional[int] = None
        self._build_layout()
        self._load_label_templates()
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
    def _load_label_templates(self) -> None:
        templates = self.label_store.list_templates()
        names = [template.name for template in templates]
        if hasattr(self, "combo_label_template"):
            self.combo_label_template["values"] = names
        if names:
            current = self.var_label_template.get()
            if current not in names:
                self.var_label_template.set(names[0])
            self._on_label_template_change()
        else:
            self.var_label_template.set("")
            self.current_template = None
            if hasattr(self, "attribute_container"):
                for child in self.attribute_container.winfo_children():
                    child.destroy()
            if hasattr(self, "label_preview"):
                self.label_preview.configure(text="Label preview: -")
    def _manage_labels(self) -> None:
        dialog = LabelManagerDialog(self.root, self.label_store)
        self.root.wait_window(dialog)
        if dialog.result:
            self.label_store = dialog.result
            try:
                self.label_store.save()
            except Exception as exc:
                messagebox.showerror("Save failed", f"Unable to save labels: {exc}", parent=self.root)
            self._load_label_templates()
    def _on_label_template_change(self) -> None:
        name = self.var_label_template.get().strip()
        template = self.label_store.get_template(name) if name else None
        self.current_template = template.copy() if template else None
        self._render_attribute_controls(self.current_template)
    def _render_attribute_controls(self, template: Optional[ClassTemplate]) -> None:
        if not hasattr(self, "attribute_container"):
            return
        for child in self.attribute_container.winfo_children():
            child.destroy()
        self.attribute_vars.clear()
        self.attribute_widgets.clear()
        self.attribute_dependents.clear()
        self.attribute_index.clear()
        self._specimen_manual = False
        self._auto_fill_specimen("")
        if not template:
            self._update_label_preview()
            return
        for attribute in template.attributes:
            self.attribute_index[attribute.name] = attribute
            self.attribute_dependents.setdefault(attribute.name, set())
        for attribute in template.attributes:
            for dependency in attribute.dependencies:
                self.attribute_dependents.setdefault(dependency, set()).add(attribute.name)
        for row, attribute in enumerate(template.attributes):
            label_parts = [attribute.name]
            if attribute.input_type == "number":
                label_parts.append("[numeric entry]")
            if attribute.dependencies:
                label_parts.append(f"(after {', '.join(attribute.dependencies)})")
            label_text = " ".join(label_parts)
            ttk.Label(self.attribute_container, text=label_text).grid(
                row=row,
                column=0,
                sticky="w",
                padx=(0, 6),
                pady=2,
            )
            var = tk.StringVar()
            if attribute.input_type == "number":
                widget = ttk.Entry(self.attribute_container, textvariable=var, state="disabled")
                widget.grid(row=row, column=1, sticky="ew", pady=2)
                var.trace_add("write", lambda *_args, name=attribute.name: self._on_attribute_change(name))
            else:
                widget = ttk.Combobox(self.attribute_container, textvariable=var, state="disabled")
                widget.grid(row=row, column=1, sticky="ew", pady=2)
                widget.bind("<<ComboboxSelected>>", lambda _event, name=attribute.name: self._on_attribute_change(name))
            self.attribute_vars[attribute.name] = var
            self.attribute_widgets[attribute.name] = widget
        self.attribute_container.columnconfigure(1, weight=1)
        self._refresh_all_attribute_options(reset=True)
    def _refresh_all_attribute_options(self, reset: bool = False) -> None:
        if not self.current_template:
            self._update_label_preview()
            return
        for attribute in self.current_template.attributes:
            self._refresh_attribute(attribute, reset=reset)
        self._update_label_preview()
    def _refresh_attribute(self, attribute: AttributeDefinition, reset: bool = False) -> None:
        widget = self.attribute_widgets.get(attribute.name)
        var = self.attribute_vars.get(attribute.name)
        if not widget or not var:
            return
        parents_ready = True
        for dependency in attribute.dependencies:
            parent_value = self.attribute_vars.get(dependency, tk.StringVar()).get()
            if not parent_value:
                parents_ready = False
                break
        if attribute.input_type != "list":
            if attribute.dependencies and not parents_ready:
                widget.configure(state="disabled")
                if reset:
                    var.set("")
            else:
                widget.configure(state="normal")
            return
        combo: ttk.Combobox = widget  # type: ignore[assignment]
        if attribute.dependencies and not parents_ready:
            combo.configure(values=(), state="disabled")
            if reset:
                var.set("")
            self._update_label_preview()
            return
        options = self._eligible_options(attribute)
        values = [option.value for option in options]
        combo.configure(values=values)
        current = var.get()
        if current not in values:
            if reset or current:
                var.set("")
        combo.configure(state="readonly" if values else "disabled")
        if len(values) == 1 and not var.get():
            var.set(values[0])
        self._update_label_preview()
    def _eligible_options(self, attribute: AttributeDefinition) -> List[AttributeOption]:
        if attribute.input_type != "list":
            return []
        if not attribute.dependencies:
            return attribute.options
        selections = {name: self.attribute_vars.get(name, tk.StringVar()).get() for name in attribute.dependencies}
        if any(not value for value in selections.values()):
            return []
        eligible: List[AttributeOption] = []
        for option in attribute.options:
            allowed = True
            for parent_name, parent_value in selections.items():
                if not parent_value:
                    allowed = False
                    break
                constraints = option.parent_constraints.get(parent_name)
                if constraints and parent_value not in constraints:
                    allowed = False
                    break
            if allowed:
                eligible.append(option)
        return eligible
    def _on_attribute_change(self, attribute_name: str) -> None:
        visited: Set[str] = set()
        queue: List[str] = [attribute_name]
        while queue:
            current = queue.pop(0)
            if current in visited:
                continue
            visited.add(current)
            for dependent in sorted(self.attribute_dependents.get(current, set())):
                attribute = self.attribute_index.get(dependent)
                if attribute:
                    self._refresh_attribute(attribute, reset=True)
                    queue.append(dependent)
        self._update_label_preview()
    def _selected_attribute_values(self) -> Dict[str, str]:
        return {name: var.get().strip() for name, var in self.attribute_vars.items()}
    def _on_specimen_var_changed(self, *_args: object) -> None:
        if self._updating_specimen:
            return
        current = self.var_specimen.get().strip()
        self._specimen_manual = bool(current)
    def _auto_fill_specimen(self, value: str) -> None:
        if self._specimen_manual:
            return
        self._updating_specimen = True
        try:
            self.var_specimen.set(value)
        finally:
            self._updating_specimen = False
    def _update_label_preview(self) -> None:
        if not hasattr(self, "label_preview"):
            return
        if not self.current_template:
            self.label_preview.configure(text="Label preview: -")
            return
        selections = self._selected_attribute_values()
        parts = [self.current_template.name]
        for attribute in self.current_template.attributes:
            value = selections.get(attribute.name, "")
            if not value:
                continue
            parts.append(value)
        preview = " > ".join(part for part in parts if part) if parts else "-"
        self.label_preview.configure(text=f"Label preview: {preview if preview else '-'}")
        self._auto_fill_specimen(preview if preview else "")
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
                f"Estimated cycle: {profile.estimated_cycle_length_sec():.2f} s\n",
            )
            self.summary_text.insert("end", f"Dwell between cycles: {profile.cycle_dwell_sec:.2f} s\n\n")
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
            cycle_dwell_sec=10.0,
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
        frame.columnconfigure(2, weight=1)
        ttk.Label(frame, text="Label category").grid(row=0, column=0, sticky="w")
        self.combo_label_template = ttk.Combobox(
            frame,
            textvariable=self.var_label_template,
            state="readonly",
            values=[template.name for template in self.label_store.list_templates()],
        )
        self.combo_label_template.grid(row=0, column=1, sticky="ew")
        self.combo_label_template.bind("<<ComboboxSelected>>", lambda _event: self._on_label_template_change())
        ttk.Button(frame, text="Manage categories...", command=self._manage_labels).grid(row=0, column=2, padx=(6, 0), sticky="w")
        warning_text = (
            "Tip: pick the broadest option first (e.g., Meat > Beef), then refine with the dependent fields. "
            "Editing categories will not update previously captured runs, so change templates sparingly."
        )
        self.label_edit_warning = ttk.Label(frame, text=warning_text, foreground="#9d174d")
        self.label_edit_warning.grid(row=1, column=0, columnspan=3, sticky="w", pady=(2, 6))
        attributes_frame = ttk.LabelFrame(frame, text="Category attributes", padding=6)
        attributes_frame.grid(row=2, column=0, columnspan=3, sticky="nsew")
        attributes_frame.columnconfigure(0, weight=1)
        attributes_frame.rowconfigure(0, weight=1)
        self.attribute_container = ttk.Frame(attributes_frame)
        self.attribute_container.grid(row=0, column=0, sticky="nsew")
        self.attribute_container.columnconfigure(1, weight=1)
        self.label_preview = ttk.Label(frame, text="Label preview: -", font=("TkDefaultFont", 9, "italic"))
        self.label_preview.grid(row=3, column=0, columnspan=3, sticky="w", pady=(6, 0))
        ttk.Label(frame, text="Specimen ID").grid(row=4, column=0, sticky="w")
        self.entry_specimen = ttk.Entry(frame, textvariable=self.var_specimen)
        self.entry_specimen.grid(row=4, column=1, columnspan=2, sticky="ew")
        self.var_specimen.trace_add("write", self._on_specimen_var_changed)
        ttk.Label(frame, text="Storage").grid(row=5, column=0, sticky="w")
        self.combo_storage = ttk.Combobox(frame, state="readonly", values=STORAGE_OPTIONS)
        self.combo_storage.grid(row=5, column=1, columnspan=2, sticky="ew")
        if STORAGE_OPTIONS:
            self.combo_storage.current(0)
        ttk.Label(frame, text="Notes").grid(row=6, column=0, sticky="nw")
        self.text_notes = tk.Text(frame, height=4)
        self.text_notes.grid(row=6, column=1, columnspan=2, sticky="ew")
        ttk.Label(frame, text="Output folder").grid(row=7, column=0, sticky="w")
        self.var_output_dir = tk.StringVar(value=str((Path.cwd() / "logs").resolve()))
        out_frame = ttk.Frame(frame)
        out_frame.columnconfigure(0, weight=1)
        out_frame.grid(row=7, column=1, columnspan=2, sticky="ew")
        self.entry_output = ttk.Entry(out_frame, textvariable=self.var_output_dir)
        self.entry_output.grid(row=0, column=0, sticky="ew")
        ttk.Button(out_frame, text="Browse...", command=self._pick_output_dir).grid(row=0, column=1, padx=(6, 0))
        ttk.Label(frame, text="Cycles to capture").grid(row=8, column=0, sticky="w")
        self.spin_cycles = tk.Spinbox(frame, from_=1, to=500, increment=1, width=8)
        self.spin_cycles.delete(0, "end")
        self.spin_cycles.insert(0, "10")
        self.spin_cycles.grid(row=8, column=1, sticky="w")
        ttk.Label(frame, text="Skip first cycles").grid(row=9, column=0, sticky="w")
        self.spin_skip = tk.Spinbox(frame, from_=0, to=100, increment=1, width=8)
        self.spin_skip.delete(0, "end")
        self.spin_skip.insert(0, "3")
        self.spin_skip.grid(row=9, column=1, sticky="w")
        self.label_error = ttk.Label(frame, text="", foreground="red")
        self.label_error.grid(row=10, column=0, columnspan=3, sticky="w")
        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=11, column=0, columnspan=3, pady=6)
        self.btn_start = ttk.Button(btn_frame, text="Start", command=self._toggle_run)
        self.btn_start.grid(row=0, column=0, padx=4)
        self.btn_stop = ttk.Button(btn_frame, text="Stop", command=self._stop_run, state="disabled")
        self.btn_stop.grid(row=0, column=1, padx=4)
        status = ttk.LabelFrame(frame, text="Status", padding=6)
        status.grid(row=12, column=0, columnspan=3, sticky="ew")
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
        graph.grid(row=13, column=0, columnspan=3, sticky="nsew", pady=(8, 0))
        graph.columnconfigure(0, weight=1)
        graph.rowconfigure(0, weight=1)
        self.graph_canvas = tk.Canvas(graph, height=200, background=self.root.cget("background"), highlightthickness=0)
        self.graph_canvas.grid(row=0, column=0, sticky="nsew")
        self.graph_canvas.bind("<Configure>", lambda _event: self._schedule_graph_redraw())
        frame.rowconfigure(13, weight=1)
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
        template_name = self.var_label_template.get().strip()
        template = self.label_store.get_template(template_name) if template_name else None
        if not template:
            self._set_error("Select a label category before starting.")
            return None
        selections = self._selected_attribute_values()
        missing = [attribute.name for attribute in template.attributes if not selections.get(attribute.name)]
        if missing:
            self._set_error(f"Select a value for: {', '.join(missing)}.")
            return None
        sample_parts = [template.name]
        for attribute in template.attributes:
            value = selections.get(attribute.name, "").strip()
            if attribute.input_type == "number":
                if not value:
                    continue
                try:
                    float(value)
                except ValueError:
                    self._set_error(f"{attribute.name} must be numeric.")
                    return None
                selections[attribute.name] = value
            if value:
                sample_parts.append(value)
        sample_name = " > ".join(part for part in sample_parts if part)
        specimen_id = self.var_specimen.get().strip()
        if not specimen_id:
            self._set_error("Specimen ID is required.")
            return None
        storage_value = self.combo_storage.get().strip() if hasattr(self, "combo_storage") else ""
        if not storage_value:
            storage_value = "unspecified"
        payload = {
            "sample_name": sample_name,
            "specimen_id": specimen_id,
            "storage": storage_value,
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
        self.progress_dwell_ms = 0.0
        self.progress_dwell_segments = 0
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
        dwell_ms = max(0.0, float(getattr(profile, "cycle_dwell_sec", 0.0)) * 1000.0)
        dwell_segments = max(total_cycles - 1, 0)
        total_ms = warmup_ms + total_cycles * total + dwell_ms * dwell_segments
        if total_ms <= 0.0:
            total_ms = 1.0
        self.progress_cycle_prefix = prefix
        self.progress_cycle_total_ms = total
        self.progress_warmup_ms = warmup_ms
        self.progress_dwell_ms = dwell_ms
        self.progress_dwell_segments = dwell_segments
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

    def _register_dwell(self, seconds: float) -> None:
        if seconds <= 0 or not self.progress_active:
            return
        dwell_ms = seconds * 1000.0
        self.progress_inferred_ms = min(self.progress_inferred_ms + dwell_ms, self.progress_total_ms)
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
                elif "__dwell__" in payload:
                    try:
                        dwell_seconds = float(payload["__dwell__"])
                    except (TypeError, ValueError):
                        dwell_seconds = 0.0
                    self._register_dwell(dwell_seconds)
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


