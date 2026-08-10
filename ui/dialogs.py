"""Small modal dialogs styled to match the rest of the UI.

tkinter's ``messagebox`` draws native light-grey dialogs, which look out of place against the
dark customtkinter windows. These are plain CTk toplevels with the same keyboard handling.
"""

from __future__ import annotations

import tkinter as tk

import customtkinter as ctk

_DANGER_COLOR = "#a03030"
_DANGER_HOVER = "#c04040"
_NEUTRAL_COLOR = "#555555"
_NEUTRAL_HOVER = "#666666"


class _Modal(ctk.CTkToplevel):
    def __init__(self, parent, title: str, message: str, *, confirm: str | None, dismiss: str):
        super().__init__(parent)
        self.title(title)
        self.resizable(False, False)
        self._parent = parent
        self._previous_grab = parent.grab_current()
        self._value = False

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=20, pady=(20, 12))
        ctk.CTkLabel(body, text=message, justify="left", wraplength=360).pack(anchor="w")

        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", padx=20, pady=(0, 16))
        if confirm is not None:
            ctk.CTkButton(
                row, text=confirm, width=90, fg_color=_DANGER_COLOR, hover_color=_DANGER_HOVER, command=self._confirm
            ).pack(side="right", padx=(8, 0))
        ctk.CTkButton(
            row,
            text=dismiss,
            width=90,
            fg_color=_NEUTRAL_COLOR if confirm is not None else None,
            hover_color=_NEUTRAL_HOVER if confirm is not None else None,
            command=self._dismiss,
        ).pack(side="right")

        self.transient(parent)
        self.protocol("WM_DELETE_WINDOW", self._dismiss)
        self.bind("<Escape>", lambda _e: self._dismiss())
        self.bind("<Return>", lambda _e: self._confirm() if confirm is not None else self._dismiss())
        self._center_on(parent)
        # grab_set() fails on an unmapped window, so wait for the window manager to show it first.
        self.wait_visibility()
        self.grab_set()
        self.focus_set()

    def _center_on(self, parent):
        self.update_idletasks()
        w, h = self.winfo_width(), self.winfo_height()
        x = parent.winfo_rootx() + (parent.winfo_width() - w) // 2
        y = parent.winfo_rooty() + (parent.winfo_height() - h) // 3
        self.geometry(f"+{max(0, x)}+{max(0, y)}")

    def _confirm(self):
        self._value = True
        self._close()

    def _dismiss(self):
        self._value = False
        self._close()

    def _close(self):
        self.grab_release()
        # Hand the grab back to the editor dialog if one opened us.
        if self._previous_grab is not None:
            try:
                self._previous_grab.grab_set()
            except tk.TclError:  # the owner may already be gone
                pass
        self.destroy()

    def show(self) -> bool:
        self.wait_window()
        return self._value


def ask_yes_no(parent, title: str, message: str, *, confirm: str = "Delete") -> bool:
    """Show a modal confirmation and return True only if the user confirmed."""
    return _Modal(parent, title, message, confirm=confirm, dismiss="Cancel").show()


def show_warning(parent, title: str, message: str) -> None:
    """Show a modal message with a single dismiss button."""
    _Modal(parent, title, message, confirm=None, dismiss="OK").show()
