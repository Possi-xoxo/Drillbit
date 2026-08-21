from collections import Counter

from app.palette_system import PaletteColor, ReferencePalette
from app.pattern_model import PatternModel, UndoStack


def palette():
    return ReferencePalette("Test", [
        PaletteColor("A", "Black", (0, 0, 0)),
        PaletteColor("B", "White", (255, 255, 255)),
        PaletteColor("C", "Red", (255, 0, 0)),
    ])


def pattern():
    return PatternModel(5, 4, [
        "A", "A", "B", "B", "B",
        "A", "A", "B", "C", "B",
        "B", "B", "B", "C", "B",
        "A", "B", "B", "B", "A",
    ], palette())


def commit(stack, label, changes):
    assert stack.push(label, changes)


def test_single_cell_is_immediately_undoable_and_redoable():
    model = pattern(); stack = UndoStack(); events = []
    stack.add_listener(lambda state: events.append((state.can_undo, state.can_redo, state.count, state.position)))
    commit(stack, "Pencil Stroke", model.set_cell(0, 0, "C"))
    assert stack.can_undo and stack.count == 1 and model.get(0, 0) == "C"
    assert events[-1] == (True, False, 1, 1)
    assert stack.undo(model) and model.get(0, 0) == "A" and stack.can_redo
    assert stack.redo(model) and model.get(0, 0) == "C" and stack.can_undo


def test_immediate_undo_needs_no_intervening_action():
    model = pattern(); stack = UndoStack(); original = list(model.cell_ids)
    commit(stack, "Pencil Stroke", model.set_cell(2, 0, "C"))
    stack.undo(model)
    assert model.cell_ids == original


def test_whole_pencil_stroke_is_one_command():
    model = pattern(); stack = UndoStack(); original = list(model.cell_ids)
    changes = model.paint([(0, 0), (1, 0), (0, 1), (1, 1)], "C")
    commit(stack, "Pencil Stroke", changes)
    assert stack.count == 1
    stack.undo(model); assert model.cell_ids == original
    stack.redo(model); assert all(model.get(x, y) == "C" for x, y in [(0, 0), (1, 0), (0, 1), (1, 1)])


def test_sequential_actions_undo_reverse_and_redo_forward():
    model = pattern(); stack = UndoStack(); states = [list(model.cell_ids)]
    commit(stack, "Stroke A", model.paint([(0, 0), (1, 0)], "C")); states.append(list(model.cell_ids))
    commit(stack, "Stroke B", model.paint([(3, 0), (4, 0)], "C")); states.append(list(model.cell_ids))
    commit(stack, "Flood Fill", model.flood_fill(2, 0, "A")); states.append(list(model.cell_ids))
    for expected in reversed(states[:-1]): stack.undo(model); assert model.cell_ids == expected
    for expected in states[1:]: stack.redo(model); assert model.cell_ids == expected


def test_no_ops_do_not_pollute_history_or_notify():
    model = pattern(); stack = UndoStack(); events = []
    stack.add_listener(lambda state: events.append(state.count)); initial_events = len(events)
    assert not stack.push("No-op Pencil", model.set_cell(0, 0, "A"))
    assert not stack.push("No-op Fill", model.flood_fill(0, 0, "A"))
    assert not stack.push("No-op Replace", model.replace_color("A", "A"))
    assert stack.count == 0 and not stack.can_undo and len(events) == initial_events


def test_flood_fill_and_replace_restore_every_cell_immediately():
    model = pattern(); stack = UndoStack(); original = list(model.cell_ids)
    fill = model.flood_fill(0, 0, "C"); commit(stack, "Flood Fill", fill); stack.undo(model)
    assert model.cell_ids == original
    replace = model.replace_color("B", "C"); commit(stack, "Replace Color", replace); stack.undo(model)
    assert model.cell_ids == original


def test_usage_counts_are_exact_through_undo_redo():
    model = pattern(); stack = UndoStack(); original = Counter(model.usage)
    commit(stack, "Pencil Stroke", model.paint([(0, 0), (1, 0), (2, 0)], "C")); edited = Counter(model.usage)
    stack.undo(model); assert model.usage == original
    stack.redo(model); assert model.usage == edited


def test_stack_state_transitions_are_synchronous():
    model = pattern(); stack = UndoStack()
    assert not stack.can_undo and not stack.can_redo
    commit(stack, "Pencil Stroke", model.set_cell(0, 0, "C"))
    assert stack.can_undo and not stack.can_redo
    stack.undo(model); assert not stack.can_undo and stack.can_redo
    stack.redo(model); assert stack.can_undo and not stack.can_redo
