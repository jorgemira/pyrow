from __future__ import annotations

import copy
from tkinter import messagebox

import customtkinter as ctk

from models.workout import DrillEntry, DrillType, Section, SectionType, Workout

_DRILL_OPTIONS = [d.label for d in DrillType]
_DRILL_BY_LABEL = {d.label: d for d in DrillType}
_SECTION_TYPE_OPTIONS = [t.label for t in SectionType]
_SECTION_TYPE_BY_LABEL = {t.label: t for t in SectionType}


class WorkoutEditorDialog(ctk.CTkToplevel):
    """Modal dialog for editing a single workout."""

    def __init__(self, parent: ctk.CTk, workout: Workout | None = None):
        super().__init__(parent)
        self.title("Edit Workout" if workout else "New Workout")
        self.geometry("550x650")
        self.resizable(False, False)

        self.workout = copy.deepcopy(workout) if workout else Workout(name="")
        self.result: Workout | None = None

        self._selected_section_idx: int | None = None
        self._selected_drill_idx: int | None = None

        self._build_ui()
        self._refresh_section_list()

        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self._on_cancel)

    def show(self) -> Workout | None:
        self.wait_window()
        return self.result

    # ── UI construction ──────────────────────────────────────────

    def _build_ui(self):
        pad = {"padx": 10, "pady": (4, 0)}

        # Name
        ctk.CTkLabel(self, text="Workout Name").pack(anchor="w", **pad)
        self._name_entry = ctk.CTkEntry(self, width=520)
        self._name_entry.insert(0, self.workout.name)
        self._name_entry.pack(**pad)

        # ── Section list ─────────────────────────────────────────
        ctk.CTkLabel(self, text="Sections").pack(anchor="w", **pad)
        self._section_frame = ctk.CTkScrollableFrame(self, height=120)
        self._section_frame.pack(fill="x", **pad)

        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(fill="x", **pad)
        ctk.CTkButton(btn_row, text="Add Section", width=100, command=self._add_section).pack(side="left", padx=(0, 4))
        self._remove_sec_btn = ctk.CTkButton(btn_row, text="Remove", width=80, command=self._remove_section, state="disabled")
        self._remove_sec_btn.pack(side="left", padx=(0, 4))
        self._up_btn = ctk.CTkButton(btn_row, text="▲", width=36, command=self._move_section_up, state="disabled")
        self._up_btn.pack(side="left", padx=(0, 4))
        self._down_btn = ctk.CTkButton(btn_row, text="▼", width=36, command=self._move_section_down, state="disabled")
        self._down_btn.pack(side="left")

        # ── Section detail area ──────────────────────────────────
        self._detail_frame = ctk.CTkFrame(self)
        self._detail_frame.pack(fill="both", expand=True, **pad)

        row1 = ctk.CTkFrame(self._detail_frame, fg_color="transparent")
        row1.pack(fill="x", padx=6, pady=(6, 0))
        ctk.CTkLabel(row1, text="Duration (sec)").pack(side="left")
        self._dur_entry = ctk.CTkEntry(row1, width=80)
        self._dur_entry.pack(side="left", padx=(4, 12))
        ctk.CTkLabel(row1, text="Stroke Rate").pack(side="left")
        self._sr_entry = ctk.CTkEntry(row1, width=80)
        self._sr_entry.pack(side="left", padx=(4, 12))
        ctk.CTkLabel(row1, text="Tension (1-8)").pack(side="left")
        self._tension_entry = ctk.CTkEntry(row1, width=50)
        self._tension_entry.pack(side="left", padx=(4, 12))
        ctk.CTkLabel(row1, text="Repeats").pack(side="left")
        self._rep_entry = ctk.CTkEntry(row1, width=60)
        self._rep_entry.pack(side="left", padx=(4, 0))

        row2 = ctk.CTkFrame(self._detail_frame, fg_color="transparent")
        row2.pack(fill="x", padx=6, pady=(6, 0))
        ctk.CTkLabel(row2, text="Section Type").pack(side="left")
        self._type_menu = ctk.CTkOptionMenu(row2, values=_SECTION_TYPE_OPTIONS, width=120)
        self._type_menu.pack(side="left", padx=(4, 12))
        ctk.CTkLabel(row2, text="Rest After (s)").pack(side="left")
        self._rest_after_entry = ctk.CTkEntry(row2, width=60)
        self._rest_after_entry.pack(side="left", padx=(4, 0))

        ctk.CTkLabel(self._detail_frame, text="Drills").pack(anchor="w", padx=6, pady=(6, 0))
        self._drill_frame = ctk.CTkScrollableFrame(self._detail_frame, height=80)
        self._drill_frame.pack(fill="x", padx=6)

        drill_btn_row = ctk.CTkFrame(self._detail_frame, fg_color="transparent")
        drill_btn_row.pack(fill="x", padx=6, pady=(4, 0))
        ctk.CTkButton(drill_btn_row, text="Add Drill", width=90, command=self._add_drill).pack(side="left", padx=(0, 4))
        self._remove_drill_btn = ctk.CTkButton(drill_btn_row, text="Remove Drill", width=100, command=self._remove_drill, state="disabled")
        self._remove_drill_btn.pack(side="left")

        drill_edit_row = ctk.CTkFrame(self._detail_frame, fg_color="transparent")
        drill_edit_row.pack(fill="x", padx=6, pady=(4, 0))
        ctk.CTkLabel(drill_edit_row, text="Type").pack(side="left")
        self._drill_type_menu = ctk.CTkOptionMenu(drill_edit_row, values=_DRILL_OPTIONS, width=160)
        self._drill_type_menu.pack(side="left", padx=(4, 12))
        ctk.CTkLabel(drill_edit_row, text="Count").pack(side="left")
        self._drill_count_entry = ctk.CTkEntry(drill_edit_row, width=60)
        self._drill_count_entry.pack(side="left", padx=(4, 0))

        # ── Save / Cancel ────────────────────────────────────────
        bottom = ctk.CTkFrame(self, fg_color="transparent")
        bottom.pack(fill="x", padx=10, pady=10)
        ctk.CTkButton(bottom, text="Cancel", fg_color="#555", hover_color="#666", width=100, command=self._on_cancel).pack(side="right", padx=(4, 0))
        ctk.CTkButton(bottom, text="Save", width=100, command=self._on_save).pack(side="right")

        self._set_detail_state("disabled")

    # ── Section list management ──────────────────────────────────

    def _refresh_section_list(self):
        for w in self._section_frame.winfo_children():
            w.destroy()
        for i, sec in enumerate(self.workout.sections):
            btn = ctk.CTkButton(
                self._section_frame,
                text=sec.summary(),
                anchor="w",
                fg_color="#3b3b3b" if i != self._selected_section_idx else "#1f6aa5",
                hover_color="#4a4a4a",
                command=lambda idx=i: self._select_section(idx),
            )
            btn.pack(fill="x", pady=1)
        self._update_section_buttons()

    def _select_section(self, idx: int):
        self._commit_drill_edits()
        self._commit_section_edits()
        self._selected_section_idx = idx
        self._selected_drill_idx = None
        self._populate_section_detail()
        self._refresh_section_list()

    def _add_section(self):
        self._commit_drill_edits()
        self._commit_section_edits()
        new_sec = Section(duration=300, stroke_rate=20)
        self.workout.sections.append(new_sec)
        self._selected_section_idx = len(self.workout.sections) - 1
        self._selected_drill_idx = None
        self._populate_section_detail()
        self._refresh_section_list()

    def _remove_section(self):
        if self._selected_section_idx is None:
            return
        self.workout.sections.pop(self._selected_section_idx)
        self._selected_section_idx = None
        self._selected_drill_idx = None
        self._set_detail_state("disabled")
        self._clear_detail_fields()
        self._refresh_section_list()

    def _move_section_up(self):
        i = self._selected_section_idx
        if i is None or i == 0:
            return
        self._commit_drill_edits()
        self._commit_section_edits()
        secs = self.workout.sections
        secs[i - 1], secs[i] = secs[i], secs[i - 1]
        self._selected_section_idx = i - 1
        self._refresh_section_list()

    def _move_section_down(self):
        i = self._selected_section_idx
        if i is None or i >= len(self.workout.sections) - 1:
            return
        self._commit_drill_edits()
        self._commit_section_edits()
        secs = self.workout.sections
        secs[i], secs[i + 1] = secs[i + 1], secs[i]
        self._selected_section_idx = i + 1
        self._refresh_section_list()

    def _update_section_buttons(self):
        has_sel = self._selected_section_idx is not None
        self._remove_sec_btn.configure(state="normal" if has_sel else "disabled")
        self._up_btn.configure(state="normal" if has_sel and self._selected_section_idx > 0 else "disabled")
        self._down_btn.configure(
            state="normal" if has_sel and self._selected_section_idx < len(self.workout.sections) - 1 else "disabled"
        )

    # ── Section detail ───────────────────────────────────────────

    def _populate_section_detail(self):
        if self._selected_section_idx is None:
            return
        sec = self.workout.sections[self._selected_section_idx]
        self._set_detail_state("normal")

        self._dur_entry.delete(0, "end")
        self._dur_entry.insert(0, str(sec.duration))
        self._sr_entry.delete(0, "end")
        self._sr_entry.insert(0, str(sec.stroke_rate))
        self._tension_entry.delete(0, "end")
        self._tension_entry.insert(0, str(sec.tension))
        self._rep_entry.delete(0, "end")
        self._rep_entry.insert(0, str(sec.repeats))
        self._type_menu.set(sec.section_type.label)
        self._rest_after_entry.delete(0, "end")
        self._rest_after_entry.insert(0, str(sec.rest_after))

        self._refresh_drill_list()

    def _commit_section_edits(self):
        if self._selected_section_idx is None:
            return
        sec = self.workout.sections[self._selected_section_idx]
        try:
            sec.duration = int(self._dur_entry.get())
        except ValueError:
            pass
        try:
            sec.stroke_rate = int(self._sr_entry.get())
        except ValueError:
            pass
        try:
            sec.tension = max(1, min(8, int(self._tension_entry.get())))
        except ValueError:
            pass
        try:
            sec.repeats = int(self._rep_entry.get())
        except ValueError:
            pass
        type_label = self._type_menu.get()
        if type_label in _SECTION_TYPE_BY_LABEL:
            sec.section_type = _SECTION_TYPE_BY_LABEL[type_label]
        try:
            sec.rest_after = max(0, int(self._rest_after_entry.get()))
        except ValueError:
            pass

    def _set_detail_state(self, state: str):
        self._dur_entry.configure(state=state)
        self._sr_entry.configure(state=state)
        self._tension_entry.configure(state=state)
        self._rep_entry.configure(state=state)
        self._type_menu.configure(state=state)
        self._rest_after_entry.configure(state=state)
        self._drill_type_menu.configure(state=state)
        self._drill_count_entry.configure(state=state)

    def _clear_detail_fields(self):
        for entry in (self._dur_entry, self._sr_entry, self._tension_entry, self._rep_entry, self._rest_after_entry, self._drill_count_entry):
            entry.configure(state="normal")
            entry.delete(0, "end")
            entry.configure(state="disabled")
        # Clear drill list
        for w in self._drill_frame.winfo_children():
            w.destroy()

    # ── Drill list management ────────────────────────────────────

    def _refresh_drill_list(self):
        for w in self._drill_frame.winfo_children():
            w.destroy()
        if self._selected_section_idx is None:
            return
        sec = self.workout.sections[self._selected_section_idx]
        for i, drill in enumerate(sec.drills):
            text = f"{drill.drill_type.label} ×{drill.count}"
            btn = ctk.CTkButton(
                self._drill_frame,
                text=text,
                anchor="w",
                fg_color="#3b3b3b" if i != self._selected_drill_idx else "#1f6aa5",
                hover_color="#4a4a4a",
                command=lambda idx=i: self._select_drill(idx),
            )
            btn.pack(fill="x", pady=1)
        self._remove_drill_btn.configure(state="normal" if self._selected_drill_idx is not None else "disabled")

    def _select_drill(self, idx: int):
        self._commit_drill_edits()
        self._selected_drill_idx = idx
        sec = self.workout.sections[self._selected_section_idx]
        drill = sec.drills[idx]
        self._drill_type_menu.set(drill.drill_type.label)
        self._drill_count_entry.delete(0, "end")
        self._drill_count_entry.insert(0, str(drill.count))
        self._refresh_drill_list()

    def _add_drill(self):
        if self._selected_section_idx is None:
            return
        self._commit_drill_edits()
        sec = self.workout.sections[self._selected_section_idx]
        sec.drills.append(DrillEntry(drill_type=DrillType.none, count=1))
        self._selected_drill_idx = len(sec.drills) - 1
        self._drill_type_menu.set(DrillType.none.label)
        self._drill_count_entry.delete(0, "end")
        self._drill_count_entry.insert(0, "1")
        self._refresh_drill_list()

    def _remove_drill(self):
        if self._selected_section_idx is None or self._selected_drill_idx is None:
            return
        sec = self.workout.sections[self._selected_section_idx]
        sec.drills.pop(self._selected_drill_idx)
        self._selected_drill_idx = None
        self._drill_count_entry.delete(0, "end")
        self._refresh_drill_list()

    def _commit_drill_edits(self):
        if self._selected_section_idx is None or self._selected_drill_idx is None:
            return
        sec = self.workout.sections[self._selected_section_idx]
        if self._selected_drill_idx >= len(sec.drills):
            return
        drill = sec.drills[self._selected_drill_idx]
        label = self._drill_type_menu.get()
        if label in _DRILL_BY_LABEL:
            drill.drill_type = _DRILL_BY_LABEL[label]
        try:
            drill.count = int(self._drill_count_entry.get())
        except ValueError:
            pass

    # ── Save / Cancel ────────────────────────────────────────────

    def _on_save(self):
        self._commit_drill_edits()
        self._commit_section_edits()
        name = self._name_entry.get().strip()
        if not name:
            messagebox.showwarning("Validation", "Workout name cannot be empty.", parent=self)
            return
        self.workout.name = name
        self.result = self.workout
        self.grab_release()
        self.destroy()

    def _on_cancel(self):
        self.result = None
        self.grab_release()
        self.destroy()
