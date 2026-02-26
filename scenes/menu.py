from __future__ import annotations

import copy
from tkinter import messagebox

import customtkinter as ctk

from animations import ANIMATION_STYLES
from models.workout import Workout
from scenes.base import Scene
from ui.workout_editor import WorkoutEditorDialog
from workout_store import load_workouts, save_workouts

_STYLE_NAMES = list(ANIMATION_STYLES.keys())


class MenuScene(Scene):
    def enter(self):
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.workouts = load_workouts()
        self._selected_idx: int | None = None

        root = ctk.CTk()
        root.title("PyRow")
        root.geometry("600x500")
        root.resizable(False, False)
        self._root = root

        # Title
        ctk.CTkLabel(root, text="PyRow", font=("", 36, "bold")).pack(pady=(18, 10))

        # Workout list
        ctk.CTkLabel(root, text="Workouts", font=("", 14)).pack(anchor="w", padx=16)
        self._list_frame = ctk.CTkScrollableFrame(root, height=280)
        self._list_frame.pack(fill="x", padx=16, pady=(0, 8))

        # Animation style selector
        style_row = ctk.CTkFrame(root, fg_color="transparent")
        style_row.pack(fill="x", padx=16, pady=(0, 6))
        ctk.CTkLabel(style_row, text="Animation Style:", font=("", 13)).pack(side="left")
        self._style_var = ctk.StringVar(value="Rowing Figure V2")
        ctk.CTkOptionMenu(style_row, variable=self._style_var,
                          values=_STYLE_NAMES, width=180).pack(side="left", padx=(8, 0))

        # Button row
        btn_row = ctk.CTkFrame(root, fg_color="transparent")
        btn_row.pack(fill="x", padx=16, pady=(0, 12))

        ctk.CTkButton(btn_row, text="Add", width=90, command=self._on_add).pack(side="left", padx=(0, 6))
        self._edit_btn = ctk.CTkButton(btn_row, text="Edit", width=90, command=self._on_edit, state="disabled")
        self._edit_btn.pack(side="left", padx=(0, 6))
        self._del_btn = ctk.CTkButton(
            btn_row, text="Delete", width=90,
            fg_color="#a03030", hover_color="#c04040",
            command=self._on_delete, state="disabled",
        )
        self._del_btn.pack(side="left", padx=(0, 6))

        self._play_btn = ctk.CTkButton(btn_row, text="Play", width=90, command=self._on_play, state="disabled")
        self._play_btn.pack(side="right", padx=(6, 0))
        ctk.CTkButton(
            btn_row, text="Exit", width=90,
            fg_color="#555555", hover_color="#666666",
            command=lambda: self._on_exit(root),
        ).pack(side="right")

        self._refresh_list()
        root.protocol("WM_DELETE_WINDOW", lambda: self._on_exit(root))
        root.mainloop()

    # ── List management ──────────────────────────────────────────

    def _refresh_list(self):
        for w in self._list_frame.winfo_children():
            w.destroy()
        self._row_buttons = []
        for i, wo in enumerate(self.workouts):
            btn = ctk.CTkButton(
                self._list_frame,
                text=wo.name,
                anchor="w",
                fg_color="#1f6aa5" if i == self._selected_idx else "#3b3b3b",
                hover_color="#4a4a4a",
                command=lambda idx=i: self._select(idx),
            )
            btn.pack(fill="x", pady=1)
            self._row_buttons.append(btn)
        self._update_buttons()

    def _select(self, idx: int):
        self._selected_idx = idx
        for i, btn in enumerate(self._row_buttons):
            btn.configure(fg_color="#1f6aa5" if i == idx else "#3b3b3b")
        self._update_buttons()

    def _update_buttons(self):
        has_sel = self._selected_idx is not None
        state = "normal" if has_sel else "disabled"
        self._edit_btn.configure(state=state)
        self._del_btn.configure(state=state)
        self._play_btn.configure(state=state)

    # ── Button actions ───────────────────────────────────────────

    def _on_add(self):
        dialog = WorkoutEditorDialog(self._root)
        result = dialog.show()
        if result:
            self.workouts.append(result)
            save_workouts(self.workouts)
            self._selected_idx = len(self.workouts) - 1
            self._refresh_list()

    def _on_edit(self):
        if self._selected_idx is None:
            return
        workout = self.workouts[self._selected_idx]
        dialog = WorkoutEditorDialog(self._root, copy.deepcopy(workout))
        result = dialog.show()
        if result:
            self.workouts[self._selected_idx] = result
            save_workouts(self.workouts)
            self._refresh_list()

    def _on_delete(self):
        if self._selected_idx is None:
            return
        name = self.workouts[self._selected_idx].name
        if messagebox.askyesno("Delete Workout", f'Delete "{name}"?', parent=self._root):
            self.workouts.pop(self._selected_idx)
            self._selected_idx = None
            save_workouts(self.workouts)
            self._refresh_list()

    def _on_play(self, root=None):
        if self._selected_idx is None:
            return
        workout = self.workouts[self._selected_idx]
        style = self._style_var.get()
        self._root.destroy()
        from scenes.animation import AnimationScene
        self.manager.switch_to(AnimationScene(self.manager, workout=workout,
                                              animation_style=style))

    def _on_exit(self, root):
        root.destroy()
        self.manager.quit()

    def exit(self):
        pass
