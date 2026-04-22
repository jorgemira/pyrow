from __future__ import annotations

import copy
import tkinter as tk
from tkinter import messagebox

import customtkinter as ctk

from models.workout import Level, Workout
from scenes.base import Scene
from ui.workout_editor import WorkoutEditorDialog
from workout_store import load_workouts, save_workouts

_TOOLTIP_DELAY_MS = 1000
_SCROLL_STEP = 0.06  # fraction of view to scroll per wheel tick
_SCROLL_EASE = 0.18  # lerp factor per animation frame (0-1, higher = snappier)
_SCROLL_INTERVAL_MS = 12  # animation frame interval

_LEVEL_FILTERS = ["All"] + [lv.label for lv in Level]
_DURATION_FILTERS = ["All", "< 20min", "20-30min", "30-45min", "> 45min"]

# Reference size — font scaling is relative to this
_REF_W = 600
_REF_H = 520


def _duration_matches(workout: Workout, filt: str) -> bool:
    mins = workout.total_duration / 60
    if filt == "< 20min":
        return mins < 20
    if filt == "20-30min":
        return 20 <= mins <= 30
    if filt == "30-45min":
        return 30 < mins <= 45
    if filt == "> 45min":
        return mins > 45
    return True


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
        self._selected_idx: int | None = None  # index into self._filtered
        self._filtered: list[int] = []  # indices into self.workouts
        self._resize_after_id: str | None = None

        root = ctk.CTk()
        root.title("PyRow")
        screen_w = root.winfo_screenwidth()
        screen_h = root.winfo_screenheight()
        win_w = min(900, max(_REF_W, int(screen_w * 0.35)))
        win_h = min(850, max(_REF_H, int(screen_h * 0.55)))
        self._ui_scale = min(win_w / _REF_W, win_h / _REF_H)
        root.geometry(f"{win_w}x{win_h}")
        root.minsize(_REF_W, _REF_H)
        self._root = root
        self._tooltip = _Tooltip(root)

        # Title
        self._title_label = ctk.CTkLabel(root, text="PyRow", font=self._font(36, bold=True))
        self._title_label.pack(pady=(18, 10))

        # Filter row
        filter_row = ctk.CTkFrame(root, fg_color="transparent")
        filter_row.pack(fill="x", padx=16, pady=(0, 6))
        self._lv_label = ctk.CTkLabel(filter_row, text="Level:", font=self._font(13))
        self._lv_label.pack(side="left")
        self._level_var = ctk.StringVar(value="All")
        self._lv_menu = ctk.CTkOptionMenu(
            filter_row,
            variable=self._level_var,
            values=_LEVEL_FILTERS,
            width=130,
            font=self._font(13),
            command=self._on_filter_change,
        )
        self._lv_menu.pack(side="left", padx=(4, 12))
        self._dur_label = ctk.CTkLabel(filter_row, text="Duration:", font=self._font(13))
        self._dur_label.pack(side="left")
        self._duration_var = ctk.StringVar(value="All")
        self._dur_menu = ctk.CTkOptionMenu(
            filter_row,
            variable=self._duration_var,
            values=_DURATION_FILTERS,
            width=130,
            font=self._font(13),
            command=self._on_filter_change,
        )
        self._dur_menu.pack(side="left", padx=(4, 0))

        # Workout list
        self._list_label = ctk.CTkLabel(root, text="Workouts", font=self._font(14))
        self._list_label.pack(anchor="w", padx=16)
        self._list_frame = ctk.CTkScrollableFrame(root, height=200)
        self._list_frame.pack(fill="both", expand=True, padx=16, pady=(0, 8))
        self._scroller = _SmoothScroller(self._list_frame)

        # Button row
        btn_row = ctk.CTkFrame(root, fg_color="transparent")
        btn_row.pack(fill="x", padx=16, pady=(0, 12))

        self._add_btn = ctk.CTkButton(btn_row, text="Add", width=90, font=self._font(13), command=self._on_add)
        self._add_btn.pack(side="left", padx=(0, 6))
        self._edit_btn = ctk.CTkButton(
            btn_row, text="Edit", width=90, font=self._font(13), command=self._on_edit, state="disabled"
        )
        self._edit_btn.pack(side="left", padx=(0, 6))
        self._del_btn = ctk.CTkButton(
            btn_row,
            text="Delete",
            width=90,
            font=self._font(13),
            fg_color="#a03030",
            hover_color="#c04040",
            command=self._on_delete,
            state="disabled",
        )
        self._del_btn.pack(side="left", padx=(0, 6))

        self._play_btn = ctk.CTkButton(
            btn_row, text="Play", width=90, font=self._font(13), command=self._on_play, state="disabled"
        )
        self._play_btn.pack(side="right", padx=(6, 0))
        self._exit_btn = ctk.CTkButton(
            btn_row,
            text="Exit",
            width=90,
            font=self._font(13),
            fg_color="#555555",
            hover_color="#666666",
            command=lambda: self._on_exit(root),
        )
        self._exit_btn.pack(side="right")

        self._refresh_list()
        root.bind("<Configure>", self._on_configure)
        root.protocol("WM_DELETE_WINDOW", lambda: self._on_exit(root))
        root.mainloop()
        root.destroy()

    # ── Font scaling ──────────────────────────────────────────────

    def _font(self, size: int, bold: bool = False) -> tuple:
        scaled = max(10, int(size * self._ui_scale))
        return ("", scaled, "bold") if bold else ("", scaled)

    def _on_configure(self, event):
        if event.widget != self._root:
            return
        if self._resize_after_id is not None:
            self._root.after_cancel(self._resize_after_id)
        self._resize_after_id = self._root.after(150, self._do_resize)

    def _do_resize(self):
        self._resize_after_id = None
        w = self._root.winfo_width()
        h = self._root.winfo_height()
        new_scale = min(w / _REF_W, h / _REF_H)
        new_scale = max(0.7, min(3.0, new_scale))
        if abs(new_scale - self._ui_scale) < 0.03:
            return
        self._ui_scale = new_scale
        self._apply_fonts()

    def _apply_fonts(self):
        self._title_label.configure(font=self._font(36, bold=True))
        self._list_label.configure(font=self._font(14))
        f13 = self._font(13)
        for w in (
            self._lv_label,
            self._dur_label,
            self._lv_menu,
            self._dur_menu,
            self._add_btn,
            self._edit_btn,
            self._del_btn,
            self._play_btn,
            self._exit_btn,
        ):
            w.configure(font=f13)
        self._refresh_list()

    # ── Filtering ─────────────────────────────────────────────

    def _apply_filters(self):
        level_filt = self._level_var.get()
        dur_filt = self._duration_var.get()
        self._filtered = []
        for i, wo in enumerate(self.workouts):
            if level_filt != "All" and wo.level.label != level_filt:
                continue
            if not _duration_matches(wo, dur_filt):
                continue
            self._filtered.append(i)

    def _on_filter_change(self, _value=None):
        self._selected_idx = None
        self._refresh_list()

    # ── List management ──────────────────────────────────────────

    def _refresh_list(self):
        self._tooltip.cancel()
        self._apply_filters()
        for w in self._list_frame.winfo_children():
            w.destroy()
        self._row_buttons = []
        btn_font = self._font(13)
        for list_pos, real_idx in enumerate(self._filtered):
            wo = self.workouts[real_idx]
            btn = ctk.CTkButton(
                self._list_frame,
                text=f"{wo.name}  ({wo.total_duration_str})",
                anchor="w",
                font=btn_font,
                fg_color="#1f6aa5" if list_pos == self._selected_idx else "#3b3b3b",
                hover_color="#4a4a4a",
                command=lambda idx=list_pos: self._select(idx),
            )
            btn.pack(fill="x", pady=1)
            desc = wo.description
            btn.bind("<Enter>", lambda e, b=btn, d=desc: self._tooltip.schedule(b, d))
            btn.bind("<Leave>", lambda e: self._tooltip.cancel())
            btn.bind("<Double-Button-1>", lambda e, idx=list_pos: self._double_click_play(idx))
            self._row_buttons.append(btn)
        self._list_label.configure(text=f"Workouts ({len(self._filtered)}/{len(self.workouts)})")
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

    def _real_idx(self) -> int | None:
        """Map filtered list selection to real workout index."""
        if self._selected_idx is None:
            return None
        return self._filtered[self._selected_idx]

    # ── Button actions ───────────────────────────────────────────

    def _on_add(self):
        dialog = WorkoutEditorDialog(self._root)
        result = dialog.show()
        if result:
            self.workouts.append(result)
            save_workouts(self.workouts)
            self._selected_idx = None
            self._refresh_list()

    def _on_edit(self):
        real = self._real_idx()
        if real is None:
            return
        workout = self.workouts[real]
        dialog = WorkoutEditorDialog(self._root, copy.deepcopy(workout))
        result = dialog.show()
        if result:
            self.workouts[real] = result
            save_workouts(self.workouts)
            self._refresh_list()

    def _on_delete(self):
        real = self._real_idx()
        if real is None:
            return
        name = self.workouts[real].name
        if messagebox.askyesno("Delete Workout", f'Delete "{name}"?', parent=self._root):
            self.workouts.pop(real)
            self._selected_idx = None
            save_workouts(self.workouts)
            self._refresh_list()

    def _double_click_play(self, idx: int):
        self._select(idx)
        self._on_play()

    def _on_play(self, root=None):
        real = self._real_idx()
        if real is None:
            return
        workout = self.workouts[real]
        from scenes.animation import AnimationScene

        self.manager.switch_to(AnimationScene(self.manager, workout=workout))
        self._root.quit()

    def _on_exit(self, root):
        self.manager.quit()
        root.quit()

    def exit(self):
        pass
