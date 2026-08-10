"""Tests for the menu scene and the themed dialogs, driving real customtkinter widgets."""

from __future__ import annotations

import pytest
from conftest import requires_display

from models.workout import Level, Section, Workout
from ui.dialogs import _Modal

pytestmark = requires_display


def workout(name: str, level: Level = Level.beginner, minutes: int = 10) -> Workout:
    return Workout(name=name, level=level, sections=[Section(duration=minutes * 60, stroke_rate=20)])


class TestSelection:
    def test_selection_survives_refiltering(self, menu_scene):
        """Selection is stored as a real workout index, not a row position."""
        menu_scene._on_row_click(3)
        selected = menu_scene._real_idx()

        menu_scene._refresh_list()

        assert menu_scene._real_idx() == selected

    def test_selection_clears_when_the_workout_is_filtered_out(self, menu_scene):
        """Editing a workout's level used to leave a stale row index behind, then IndexError."""
        menu_scene._level_var.set("Beginner")
        menu_scene._refresh_list()
        last_row = len(menu_scene._filtered) - 1
        menu_scene._on_row_click(last_row)
        real = menu_scene._real_idx()
        assert real is not None

        menu_scene.workouts[real].level = Level.advanced  # what the editor does on save
        menu_scene._refresh_list()

        assert menu_scene._real_idx() is None
        assert menu_scene._play_btn.cget("state") == "disabled"

    def test_play_is_a_no_op_when_the_selection_is_filtered_out(self, menu_scene):
        menu_scene._level_var.set("Beginner")
        menu_scene._refresh_list()
        menu_scene._on_row_click(len(menu_scene._filtered) - 1)
        menu_scene.workouts[menu_scene._real_idx()].level = Level.advanced
        menu_scene._refresh_list()

        menu_scene._on_play()  # must not raise

        assert menu_scene.manager.switched_to is None

    def test_only_the_selected_row_is_highlighted(self, menu_scene):
        menu_scene._on_row_click(3)

        highlighted = [
            pos for pos in range(menu_scene._rows_shown) if menu_scene._row_buttons[pos].cget("fg_color") == "#1f6aa5"
        ]

        assert highlighted == [3]

    def test_action_buttons_follow_the_selection(self, menu_scene):
        assert menu_scene._edit_btn.cget("state") == "disabled"

        menu_scene._on_row_click(0)

        for button in (menu_scene._edit_btn, menu_scene._del_btn, menu_scene._play_btn):
            assert button.cget("state") == "normal"


class TestKeyboardNavigation:
    def test_down_selects_the_first_row_then_advances(self, menu_scene):
        menu_scene._move_selection(1)
        assert menu_scene._visible_position() == 0

        menu_scene._move_selection(1)
        assert menu_scene._visible_position() == 1

    def test_navigation_clamps_at_both_ends(self, menu_scene):
        menu_scene._move_selection(-1)
        menu_scene._move_selection(-1)
        assert menu_scene._visible_position() == 0

        menu_scene._select_row_at(len(menu_scene._filtered) - 1)
        menu_scene._move_selection(1)
        assert menu_scene._visible_position() == len(menu_scene._filtered) - 1

    def test_selecting_a_row_below_the_fold_scrolls_it_into_view(self, menu_scene):
        canvas = menu_scene._list_frame._parent_canvas
        assert canvas.yview()[0] == 0.0

        menu_scene._select_row_at(len(menu_scene._filtered) - 1)
        menu_scene._root.update_idletasks()

        assert canvas.yview()[0] > 0.5, "the last row should be scrolled into view"

    def test_scrolling_into_view_keeps_the_smooth_scroller_in_sync(self, menu_scene):
        """Otherwise the next wheel tick animates from a stale position and jumps."""
        menu_scene._select_row_at(len(menu_scene._filtered) - 1)
        menu_scene._root.update_idletasks()
        position = menu_scene._list_frame._parent_canvas.yview()[0]

        assert menu_scene._scroller._target == pytest.approx(position)
        assert menu_scene._scroller._current == pytest.approx(position)

    def test_navigation_does_nothing_with_an_empty_list(self, menu_scene):
        menu_scene.workouts = []
        menu_scene._refresh_list()

        menu_scene._move_selection(1)  # must not raise

        assert menu_scene._real_idx() is None


class TestRowPool:
    def test_rows_are_reused_rather_than_rebuilt(self, menu_scene):
        """Recreating 116 CTkButtons per refresh cost ~2s; the pool must be reused."""
        before = list(menu_scene._row_buttons)

        menu_scene._level_var.set("Advanced")
        menu_scene._refresh_list()
        menu_scene._level_var.set("All")
        menu_scene._refresh_list()

        assert menu_scene._row_buttons == before, "row widgets were destroyed and recreated"

    def test_visible_rows_match_the_filter_in_order(self, menu_scene):
        menu_scene._level_var.set("Intermediate")
        menu_scene._refresh_list()

        expected = [
            f"{menu_scene.workouts[i].name}  ({menu_scene.workouts[i].total_duration_str})"
            for i in menu_scene._filtered
        ]
        shown = [menu_scene._row_buttons[pos].cget("text") for pos in range(menu_scene._rows_shown)]

        assert shown == expected

    def test_surplus_rows_are_unmapped(self, menu_scene):
        total = menu_scene._rows_shown

        menu_scene._level_var.set("Advanced")
        menu_scene._refresh_list()
        menu_scene._root.update_idletasks()

        assert menu_scene._rows_shown < total
        assert not menu_scene._row_buttons[menu_scene._rows_shown].winfo_ismapped()

    def test_font_rescale_does_not_rebuild_the_list(self, menu_scene):
        before = list(menu_scene._row_buttons)

        menu_scene._ui_scale *= 1.4
        menu_scene._apply_fonts()

        assert menu_scene._row_buttons == before


class TestEmptyState:
    def test_message_appears_only_when_nothing_matches(self, menu_scene):
        menu_scene._root.update_idletasks()
        assert not menu_scene._empty_label.winfo_ismapped()

        menu_scene.workouts = []
        menu_scene._refresh_list()
        menu_scene._root.update_idletasks()

        assert menu_scene._empty_label.winfo_ismapped()
        assert menu_scene._rows_shown == 0

    def test_message_disappears_again(self, menu_scene):
        original = menu_scene.workouts
        menu_scene.workouts = []
        menu_scene._refresh_list()

        menu_scene.workouts = original
        menu_scene._refresh_list()
        menu_scene._root.update_idletasks()

        assert not menu_scene._empty_label.winfo_ismapped()

    def test_count_label_tracks_the_filter(self, menu_scene):
        menu_scene._level_var.set("Advanced")
        menu_scene._refresh_list()

        total = len(menu_scene.workouts)
        assert menu_scene._list_label.cget("text") == f"Workouts ({len(menu_scene._filtered)}/{total})"


class TestFilterPredicate:
    def test_matches_filters_agrees_with_the_visible_list(self, menu_scene):
        menu_scene._level_var.set("Intermediate")
        menu_scene._duration_var.set("20-30min")
        menu_scene._refresh_list()

        expected = [i for i, wo in enumerate(menu_scene.workouts) if menu_scene._matches_filters(wo)]

        assert menu_scene._filtered == expected

    def test_a_new_workout_hidden_by_filters_is_detected(self, menu_scene):
        menu_scene._level_var.set("Beginner")

        assert not menu_scene._matches_filters(workout("New", Level.advanced))
        assert menu_scene._matches_filters(workout("New", Level.beginner))


class TestDialogs:
    def test_confirm_returns_true(self, ctk_root):
        dialog = _Modal(ctk_root, "Delete Workout", 'Delete "X"?', confirm="Delete", dismiss="Cancel")
        dialog.after_idle(dialog._confirm)

        assert dialog.show() is True

    def test_dismiss_returns_false(self, ctk_root):
        dialog = _Modal(ctk_root, "Delete Workout", 'Delete "X"?', confirm="Delete", dismiss="Cancel")
        dialog.after_idle(dialog._dismiss)

        assert dialog.show() is False

    def test_warning_has_a_single_button_and_returns_false(self, ctk_root):
        dialog = _Modal(ctk_root, "Validation", "Name cannot be empty.", confirm=None, dismiss="OK")
        dialog.after_idle(dialog._dismiss)

        assert dialog.show() is False

    def test_grab_is_released_so_the_app_is_not_frozen(self, ctk_root):
        dialog = _Modal(ctk_root, "Delete Workout", "?", confirm="Delete", dismiss="Cancel")
        dialog.after_idle(dialog._dismiss)
        dialog.show()

        assert ctk_root.grab_current() is None

    def test_grab_returns_to_the_editor_that_opened_it(self, ctk_root):
        """A nested modal that swallows the grab leaves the editor permanently unclickable."""
        from ui.workout_editor import WorkoutEditorDialog

        editor = WorkoutEditorDialog(ctk_root)
        editor.update_idletasks()
        assert ctk_root.grab_current() is editor

        dialog = _Modal(editor, "Validation", "Add a section.", confirm=None, dismiss="OK")
        dialog.after_idle(dialog._dismiss)
        dialog.show()

        assert ctk_root.grab_current() is editor
        editor._on_cancel()


class TestEditorValidation:
    def test_a_workout_with_no_sections_cannot_be_saved(self, ctk_root, monkeypatch):
        from ui import workout_editor

        warnings: list[str] = []
        monkeypatch.setattr(workout_editor, "show_warning", lambda parent, title, msg: warnings.append(msg))

        editor = workout_editor.WorkoutEditorDialog(ctk_root)
        editor._name_entry.insert(0, "No Sections")
        editor._on_save()

        assert editor.result is None
        assert "at least one section" in warnings[-1]
        editor._on_cancel()

    def test_an_empty_name_cannot_be_saved(self, ctk_root, monkeypatch):
        from ui import workout_editor

        warnings: list[str] = []
        monkeypatch.setattr(workout_editor, "show_warning", lambda parent, title, msg: warnings.append(msg))

        editor = workout_editor.WorkoutEditorDialog(ctk_root, workout("X"))
        editor._name_entry.delete(0, "end")
        editor._on_save()

        assert editor.result is None
        assert "name cannot be empty" in warnings[-1]
        editor._on_cancel()

    def test_out_of_range_values_are_clamped_to_something_playable(self, ctk_root):
        from ui.workout_editor import WorkoutEditorDialog
        from workout_player import WorkoutPlayer

        editor = WorkoutEditorDialog(ctk_root, workout("Clamp me"))
        editor._select_section(0)
        for entry, bad in [
            (editor._dur_entry, "0"),
            (editor._sr_entry, "0"),
            (editor._rep_entry, "-3"),
            (editor._tension_entry, "99"),
        ]:
            entry.delete(0, "end")
            entry.insert(0, bad)

        editor._commit_section_edits()
        section = editor.workout.sections[0]

        assert (section.duration, section.stroke_rate, section.repeats, section.tension) == (1, 1, 1, 8)
        WorkoutPlayer(editor.workout)  # must be playable
        editor._on_cancel()
