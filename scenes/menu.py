from __future__ import annotations

import copy
import tkinter as tk
from pathlib import Path

import customtkinter as ctk

from models.workout import Level, Workout
from scenes.base import Scene
from ui.dialogs import ask_yes_no, show_warning
from ui.workout_editor import WorkoutEditorDialog
from workout_store import load_workouts, save_workouts

_TOOLTIP_DELAY_MS = 1000
_SCROLL_STEP = 0.06  # fraction of view to scroll per wheel tick
_SCROLL_EASE = 0.18  # lerp factor per animation frame (0-1, higher = snappier)
_SCROLL_INTERVAL_MS = 12  # animation frame interval

_LEVEL_FILTERS = ["All"] + [lv.label for lv in Level]
_DURATION_FILTERS = ["All", "< 20min", "20-30min", "30-45min", "> 45min"]

_ROW_NORMAL = "#3b3b3b"
_ROW_SELECTED = "#1f6aa5"
_ROW_HOVER = "#4a4a4a"
_MUTED_TEXT = "#888888"
_DANGER = "#a03030"
_DANGER_HOVER = "#c04040"
_NEUTRAL = "#555555"
_NEUTRAL_HOVER = "#666666"

_ICON_FILE = Path(__file__).parent.parent / "pyrow.png"

_TOOLTIP_BG = "#2b2b2b"
_TOOLTIP_FG = "#dcdcdc"

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

    def sync(self):
        """Adopt the canvas position after something else scrolled it (e.g. keyboard nav)."""
        self._target = self._current = float(self._canvas.yview()[0])

    def _pointer_over_list(self) -> bool:
        """The wheel is bound app-wide, so ignore ticks aimed at the filters or buttons."""
        widget = self._canvas.winfo_containing(self._canvas.winfo_pointerx(), self._canvas.winfo_pointery())
        while widget is not None:
            if widget is self._canvas:
                return True
            widget = getattr(widget, "master", None)
        return False

    def _scroll(self, delta: float):
        if not self._pointer_over_list():
            return
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
        tip = tk.Toplevel(self._root)
        tip.wm_overrideredirect(True)
        label = tk.Label(
            tip,
            text=text,
            background=_TOOLTIP_BG,
            foreground=_TOOLTIP_FG,
            padx=8,
            pady=4,
            wraplength=400,
            justify="left",
        )
        label.pack()

        # Keep the tooltip on screen: flip above the row near the bottom edge, clamp at the right.
        tip.update_idletasks()
        tip_w, tip_h = tip.winfo_width(), tip.winfo_height()
        x = min(widget.winfo_rootx(), self._root.winfo_screenwidth() - tip_w - 8)
        y = widget.winfo_rooty() + widget.winfo_height() + 4
        if y + tip_h > self._root.winfo_screenheight() - 8:
            y = widget.winfo_rooty() - tip_h - 4
        tip.wm_geometry(f"+{max(0, x)}+{max(0, y)}")
        self._tip = tip

    def _hide(self):
        if self._tip is not None:
            self._tip.destroy()
            self._tip = None


class MenuScene(Scene):
    def enter(self):
        """Build the menu window and run tkinter's event loop until a workout is chosen."""
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.workouts = load_workouts()
        self._selected: int | None = None  # index into self.workouts, survives refiltering
        self._filtered: list[int] = []  # indices into self.workouts
        self._resize_after_id: str | None = None

        # Row buttons are pooled and reused; rebuilding them all is ~2s for a 116-workout library.
        self._row_buttons: list[ctk.CTkButton] = []
        self._rows_shown: int = 0

        root = self._build_window()
        self._build_title(root)
        self._build_filter_row(root)
        self._build_workout_list(root)
        self._build_button_row(root)

        self._refresh_list()
        self._bind_keys(root)
        root.mainloop()
        root.destroy()

    def _build_window(self) -> ctk.CTk:
        root = ctk.CTk()
        root.title("PyRow")
        win_w = min(900, max(_REF_W, int(root.winfo_screenwidth() * 0.35)))
        win_h = min(850, max(_REF_H, int(root.winfo_screenheight() * 0.55)))
        self._ui_scale = min(win_w / _REF_W, win_h / _REF_H)
        root.geometry(f"{win_w}x{win_h}")
        root.minsize(_REF_W, _REF_H)
        self._root = root
        self._tooltip = _Tooltip(root)
        self._set_window_icon(root)
        return root

    def _build_title(self, root: ctk.CTk) -> None:
        self._title_label = ctk.CTkLabel(root, text="PyRow", font=self._font(36, bold=True))
        self._title_label.pack(pady=(18, 10))

    def _build_filter_row(self, root: ctk.CTk) -> None:
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

    def _build_workout_list(self, root: ctk.CTk) -> None:
        self._list_label = ctk.CTkLabel(root, text="Workouts", font=self._font(14))
        self._list_label.pack(anchor="w", padx=16)
        self._list_frame = ctk.CTkScrollableFrame(root, height=200)
        self._list_frame.pack(fill="both", expand=True, padx=16, pady=(0, 8))
        self._scroller = _SmoothScroller(self._list_frame)
        self._empty_label = ctk.CTkLabel(
            self._list_frame,
            text="No workouts match these filters.",
            text_color=_MUTED_TEXT,
            font=self._font(13),
        )

    def _build_button_row(self, root: ctk.CTk) -> None:
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
            fg_color=_DANGER,
            hover_color=_DANGER_HOVER,
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
            fg_color=_NEUTRAL,
            hover_color=_NEUTRAL_HOVER,
            command=self._on_exit,
        )
        self._exit_btn.pack(side="right")

    def _bind_keys(self, root: ctk.CTk) -> None:
        root.bind("<Configure>", self._on_configure)
        root.bind("<Up>", lambda _e: self._move_selection(-1))
        root.bind("<Down>", lambda _e: self._move_selection(1))
        root.bind("<Home>", lambda _e: self._select_row_at(0))
        root.bind("<End>", lambda _e: self._select_row_at(len(self._filtered) - 1))
        root.bind("<Return>", lambda _e: self._on_play())
        root.bind("<Escape>", lambda _e: self._on_exit())
        root.protocol("WM_DELETE_WINDOW", self._on_exit)

    def _set_window_icon(self, root: ctk.CTk) -> None:
        """Apply the app icon, ignoring failures — Tk's PNG support varies by build."""
        try:
            self._icon_image = tk.PhotoImage(file=str(_ICON_FILE))  # must outlive the call
            root.iconphoto(True, self._icon_image)
        except tk.TclError, OSError:
            pass

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
        self._empty_label.configure(font=f13)
        for btn in self._row_buttons:
            btn.configure(font=f13)

    # ── Filtering ─────────────────────────────────────────────

    def _matches_filters(self, workout: Workout) -> bool:
        level_filt = self._level_var.get()
        if level_filt != "All" and workout.level.label != level_filt:
            return False
        return _duration_matches(workout, self._duration_var.get())

    def _apply_filters(self):
        self._filtered = [i for i, wo in enumerate(self.workouts) if self._matches_filters(wo)]

    def _on_filter_change(self, _value=None):
        self._selected = None
        self._refresh_list()

    # ── List management ──────────────────────────────────────────

    def _make_row_button(self) -> ctk.CTkButton:
        """Create a pooled row button bound to its fixed position in the visible list."""
        pos = len(self._row_buttons)
        btn = ctk.CTkButton(
            self._list_frame,
            text="",
            anchor="w",
            font=self._font(13),
            hover_color=_ROW_HOVER,
            command=lambda p=pos: self._on_row_click(p),
        )
        btn.bind("<Enter>", lambda _e, p=pos: self._on_row_enter(p))
        btn.bind("<Leave>", lambda _e: self._tooltip.cancel())
        btn.bind("<Double-Button-1>", lambda _e, p=pos: self._on_row_double_click(p))
        return btn

    def _row_workout(self, pos: int) -> Workout | None:
        """Return the workout shown at visible row *pos*, or None if the row is stale."""
        if pos >= len(self._filtered):
            return None
        return self.workouts[self._filtered[pos]]

    def _on_row_click(self, pos: int):
        if pos < len(self._filtered):
            self._select(self._filtered[pos])

    def _on_row_enter(self, pos: int):
        wo = self._row_workout(pos)
        if wo is not None:
            self._tooltip.schedule(self._row_buttons[pos], wo.description)

    def _on_row_double_click(self, pos: int):
        if pos < len(self._filtered):
            self._select(self._filtered[pos])
            self._on_play()

    def _refresh_list(self):
        self._tooltip.cancel()
        self._apply_filters()

        while len(self._row_buttons) < len(self._filtered):
            self._row_buttons.append(self._make_row_button())

        for pos, real_idx in enumerate(self._filtered):
            wo = self.workouts[real_idx]
            btn = self._row_buttons[pos]
            btn.configure(
                text=f"{wo.name}  ({wo.total_duration_str})",
                fg_color=_ROW_SELECTED if real_idx == self._selected else _ROW_NORMAL,
            )
            if pos >= self._rows_shown:
                btn.pack(fill="x", pady=1)
        for pos in range(len(self._filtered), self._rows_shown):
            self._row_buttons[pos].pack_forget()
        self._rows_shown = len(self._filtered)

        if self._filtered:
            self._empty_label.pack_forget()
        else:
            self._empty_label.pack(pady=24)

        self._list_label.configure(text=f"Workouts ({len(self._filtered)}/{len(self.workouts)})")
        self._update_buttons()

    def _select(self, real_idx: int):
        previous = self._selected
        self._selected = real_idx
        for pos in range(self._rows_shown):
            shown = self._filtered[pos]
            if shown in (previous, real_idx):
                self._row_buttons[pos].configure(fg_color=_ROW_SELECTED if shown == real_idx else _ROW_NORMAL)
        self._update_buttons()

    # ── Keyboard navigation ──────────────────────────────────────

    def _visible_position(self) -> int | None:
        """Return the visible row position of the selection, or None."""
        real = self._real_idx()
        return self._filtered.index(real) if real is not None else None

    def _move_selection(self, delta: int):
        if not self._filtered:
            return
        current = self._visible_position()
        target = 0 if current is None else max(0, min(len(self._filtered) - 1, current + delta))
        self._select_row_at(target)

    def _select_row_at(self, pos: int):
        if 0 <= pos < len(self._filtered):
            self._select(self._filtered[pos])
            self._scroll_into_view(pos)

    def _scroll_into_view(self, pos: int):
        """Keep the keyboard-selected row visible without jumping the whole list."""
        canvas = self._list_frame._parent_canvas
        btn = self._row_buttons[pos]
        self._root.update_idletasks()
        # CTkScrollableFrame *is* the inner content frame — it is a tkinter.Frame inside the canvas.
        content_h = self._list_frame.winfo_height()
        view_h = canvas.winfo_height()
        if content_h <= view_h:
            return

        row_top, row_h = btn.winfo_y(), btn.winfo_height()
        view_top = canvas.yview()[0] * content_h
        if row_top < view_top:
            canvas.yview_moveto(row_top / content_h)
        elif row_top + row_h > view_top + view_h:
            canvas.yview_moveto((row_top + row_h - view_h) / content_h)
        self._scroller.sync()

    def _update_buttons(self):
        state = "normal" if self._real_idx() is not None else "disabled"
        self._edit_btn.configure(state=state)
        self._del_btn.configure(state=state)
        self._play_btn.configure(state=state)

    def _real_idx(self) -> int | None:
        """Return the selected workout index, or None when nothing selected or it is filtered out."""
        if self._selected is None or self._selected not in self._filtered:
            return None
        return self._selected

    # ── Button actions ───────────────────────────────────────────

    def _on_add(self):
        dialog = WorkoutEditorDialog(self._root)
        result = dialog.show()
        if result:
            self.workouts.append(result)
            save_workouts(self.workouts)
            self._selected = len(self.workouts) - 1
            # Clear filters that would otherwise hide what was just created.
            if not self._matches_filters(result):
                self._level_var.set("All")
                self._duration_var.set("All")
            self._refresh_list()
            position = self._visible_position()
            if position is not None:
                self._scroll_into_view(position)

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
        if ask_yes_no(self._root, "Delete Workout", f'Delete "{name}"?'):
            self.workouts.pop(real)
            self._selected = None
            save_workouts(self.workouts)
            self._refresh_list()

    def _on_play(self):
        real = self._real_idx()
        if real is None:
            return
        workout = self.workouts[real]
        if not workout.flatten_sections():
            show_warning(
                self._root,
                "Cannot Play",
                f'"{workout.name}" has no playable sections.\nEdit it and add a section with at least one repeat.',
            )
            return
        from scenes.animation import AnimationScene

        self.manager.switch_to(AnimationScene(self.manager, workout=workout))
        self._root.quit()

    def _on_exit(self):
        self.manager.quit()
        self._root.quit()

    def exit(self):
        self._tooltip.cancel()
