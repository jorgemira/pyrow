from __future__ import annotations

import copy
import tkinter as tk
from tkinter import messagebox

import customtkinter as ctk

from scenes.base import Scene
from ui.workout_editor import WorkoutEditorDialog
from workout_store import load_workouts, save_workouts

_TOOLTIP_DELAY_MS = 1000
_SCROLL_STEP = 0.06  # fraction of view to scroll per wheel tick
_SCROLL_EASE = 0.18  # lerp factor per animation frame (0-1, higher = snappier)
_SCROLL_INTERVAL_MS = 12  # animation frame interval


class _SmoothScroller:
    """Smooth-scroll overlay for a CTkScrollableFrame's internal canvas."""

    def __init__(self, scrollable_frame: ctk.CTkScrollableFrame):
        self._canvas = scrollable_frame._parent_canvas
        self._target: float = 0.0
        self._current: float = 0.0
        self._animating = False

        # Unbind default scroll, bind our handler
        self._canvas.unbind_all("<Button-4>")
        self._canvas.unbind_all("<Button-5>")
        self._canvas.unbind_all("<MouseWheel>")
        self._canvas.bind_all("<Button-4>", self._on_scroll_up)
        self._canvas.bind_all("<Button-5>", self._on_scroll_down)
        self._canvas.bind_all("<MouseWheel>", self._on_mousewheel)

    def _on_scroll_up(self, _event):
        self._scroll(-_SCROLL_STEP)

    def _on_scroll_down(self, _event):
        self._scroll(_SCROLL_STEP)

    def _on_mousewheel(self, event):
        # Windows/macOS: event.delta is positive for up, negative for down
        if event.delta > 0:
            self._scroll(-_SCROLL_STEP)
        elif event.delta < 0:
            self._scroll(_SCROLL_STEP)

    def _scroll(self, delta: float):
        self._target = max(0.0, min(1.0, self._target + delta))
        if not self._animating:
            # Sync current position from canvas
            self._current = float(self._canvas.yview()[0])
            self._animating = True
            self._animate()

    def _animate(self):
        diff = self._target - self._current
        if abs(diff) < 0.001:
            self._current = self._target
            self._canvas.yview_moveto(self._current)
            self._animating = False
            return
        self._current += diff * _SCROLL_EASE
        self._canvas.yview_moveto(self._current)
        self._canvas.after(_SCROLL_INTERVAL_MS, self._animate)


class _Tooltip:
    """Hover tooltip that appears after a delay."""

    def __init__(self, root: ctk.CTk):
        self._root = root
        self._tip: tk.Toplevel | None = None
        self._after_id: str | None = None

    def schedule(self, widget: ctk.CTkBaseClass, text: str):
        self.cancel()
        if not text:
            return
        self._after_id = self._root.after(_TOOLTIP_DELAY_MS, lambda: self._show(widget, text))

    def cancel(self):
        if self._after_id is not None:
            self._root.after_cancel(self._after_id)
            self._after_id = None
        self._hide()

    def _show(self, widget: ctk.CTkBaseClass, text: str):
        self._after_id = None
        self._hide()
        x = widget.winfo_rootx()
        y = widget.winfo_rooty() + widget.winfo_height() + 4
        tip = tk.Toplevel(self._root)
        tip.wm_overrideredirect(True)
        tip.wm_geometry(f"+{x}+{y}")
        label = tk.Label(tip, text=text, background="#333333", foreground="#dddddd", padx=8, pady=4, wraplength=400)
        label.pack()
        self._tip = tip

    def _hide(self):
        if self._tip is not None:
            self._tip.destroy()
            self._tip = None


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
        self._tooltip = _Tooltip(root)

        # Title
        ctk.CTkLabel(root, text="PyRow", font=("", 36, "bold")).pack(pady=(18, 10))

        # Workout list
        ctk.CTkLabel(root, text="Workouts", font=("", 14)).pack(anchor="w", padx=16)
        self._list_frame = ctk.CTkScrollableFrame(root, height=280)
        self._list_frame.pack(fill="x", padx=16, pady=(0, 8))
        self._scroller = _SmoothScroller(self._list_frame)

        # Button row
        btn_row = ctk.CTkFrame(root, fg_color="transparent")
        btn_row.pack(fill="x", padx=16, pady=(0, 12))

        ctk.CTkButton(btn_row, text="Add", width=90, command=self._on_add).pack(side="left", padx=(0, 6))
        self._edit_btn = ctk.CTkButton(btn_row, text="Edit", width=90, command=self._on_edit, state="disabled")
        self._edit_btn.pack(side="left", padx=(0, 6))
        self._del_btn = ctk.CTkButton(
            btn_row,
            text="Delete",
            width=90,
            fg_color="#a03030",
            hover_color="#c04040",
            command=self._on_delete,
            state="disabled",
        )
        self._del_btn.pack(side="left", padx=(0, 6))

        self._play_btn = ctk.CTkButton(btn_row, text="Play", width=90, command=self._on_play, state="disabled")
        self._play_btn.pack(side="right", padx=(6, 0))
        ctk.CTkButton(
            btn_row,
            text="Exit",
            width=90,
            fg_color="#555555",
            hover_color="#666666",
            command=lambda: self._on_exit(root),
        ).pack(side="right")

        self._refresh_list()
        root.protocol("WM_DELETE_WINDOW", lambda: self._on_exit(root))
        root.mainloop()

    # ── List management ──────────────────────────────────────────

    def _refresh_list(self):
        self._tooltip.cancel()
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
            desc = wo.description
            btn.bind("<Enter>", lambda e, b=btn, d=desc: self._tooltip.schedule(b, d))
            btn.bind("<Leave>", lambda e: self._tooltip.cancel())
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
        self._root.destroy()
        from scenes.animation import AnimationScene

        self.manager.switch_to(AnimationScene(self.manager, workout=workout))

    def _on_exit(self, root):
        root.destroy()
        self.manager.quit()

    def exit(self):
        pass
