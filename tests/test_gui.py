"""GUI-level tests (pytest-qt) for CopyTool.

Run headless via QT_QPA_PLATFORM=offscreen (set in conftest.py). Skipped
entirely if PySide6 / pytest-qt are unavailable.
"""

import pytest

pytest.importorskip('PySide6')
pytest.importorskip('pytestqt')

from PySide6.QtCore import QSettings, QCoreApplication  # noqa: E402

from copy_tool import persistence  # noqa: E402
from copy_tool.widgets import CardListWidget, CopyJobCard  # noqa: E402


@pytest.fixture
def isolated_settings(tmp_path):
    """Point QSettings at a temp dir so tests never touch real user settings."""
    QCoreApplication.setOrganizationName('EduceLabTest')
    QCoreApplication.setApplicationName('CopyToolTest')
    QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, str(tmp_path))
    QSettings.setDefaultFormat(QSettings.IniFormat)
    s = QSettings()
    s.clear()
    s.sync()
    yield s
    s.clear()
    s.sync()


# --- CardListWidget ----------------------------------------------------------

def test_add_and_list_cards(qtbot):
    w = CardListWidget()
    qtbot.addWidget(w)
    assert w.card_list == []

    w.card_list = [('/s1', '/t1'), ('/s2', '/t2')]
    assert w.card_list == [('/s1', '/t1'), ('/s2', '/t2')]
    assert len(w.cards()) == 2
    # 1-based labels assigned in order.
    assert [c.list_index for c in w.cards()] == [1, 2]


def test_remove_card_by_identity_renumbers(qtbot):
    w = CardListWidget()
    qtbot.addWidget(w)
    w.card_list = [('/s1', '/t1'), ('/s2', '/t2'), ('/s3', '/t3')]

    middle = w.cards()[1]
    w.remove_card(middle)

    assert w.card_list == [('/s1', '/t1'), ('/s3', '/t3')]
    assert [c.list_index for c in w.cards()] == [1, 2]


def test_remove_all_cards_allowed(qtbot):
    w = CardListWidget()
    qtbot.addWidget(w)
    w.card_list = [('/s1', '/t1')]
    w.remove_card(w.cards()[0])
    assert w.card_list == []  # empty is a valid state now


def test_remove_unknown_card_is_noop(qtbot):
    w = CardListWidget()
    qtbot.addWidget(w)
    w.card_list = [('/s1', '/t1')]
    stray = CopyJobCard()
    qtbot.addWidget(stray)
    w.remove_card(stray)  # not in the list — must not raise or remove anything
    assert len(w.cards()) == 1


def test_close_button_emits_and_removes(qtbot):
    w = CardListWidget()
    qtbot.addWidget(w)
    w.card_list = [('/s1', '/t1'), ('/s2', '/t2')]
    first = w.cards()[0]
    first._on_click_close()
    assert w.card_list == [('/s2', '/t2')]


def test_card_list_setter_skips_malformed(qtbot):
    w = CardListWidget()
    qtbot.addWidget(w)
    # A malformed entry (single value) must be skipped, not crash.
    w.card_list = [('/s1', '/t1'), ('oops',), ('/s2', '/t2')]
    assert w.card_list == [('/s1', '/t1'), ('/s2', '/t2')]


# --- MainWindow settings: migration / empty / round-trip ---------------------

@pytest.fixture
def main_window(qtbot, isolated_settings, monkeypatch):
    """Build a MainWindow with rclone faked as installed."""
    import copy_tool.rclone as rclone
    monkeypatch.setattr(rclone, 'is_installed', lambda: True)
    monkeypatch.setattr(rclone, 'executable_path', lambda: 'rclone')

    def _make():
        from copy_tool.main import MainWindow
        win = MainWindow()
        qtbot.addWidget(win)
        return win

    return _make


def test_first_launch_seeds_one_card(main_window):
    win = main_window()
    assert len(win._cards_widget.cards()) == 1


def test_empty_saved_list_respected(main_window, isolated_settings):
    isolated_settings.setValue(persistence.CARDS_KEY,
                               persistence.serialize_cards([]))
    isolated_settings.setValue(persistence.VERSION_KEY,
                               persistence.SETTINGS_VERSION)
    isolated_settings.sync()

    win = main_window()
    # A genuinely empty saved list is honored — no card seeded.
    assert win._cards_widget.cards() == []


def test_saved_cards_round_trip(main_window, isolated_settings):
    isolated_settings.setValue(persistence.CARDS_KEY,
                               persistence.serialize_cards(
                                   [('/s1', '/t1'), ('/s2', '/t2')]))
    isolated_settings.sync()

    win = main_window()
    assert win._cards_widget.card_list == [('/s1', '/t1'), ('/s2', '/t2')]


def test_legacy_cards_migrated(main_window, isolated_settings):
    # Simulate a pre-1.3.0 store: a legacy 'cards' list, no cards_json.
    isolated_settings.setValue(persistence.LEGACY_CARDS_KEY,
                               [['/old1', '/new1'], ['/old2', '/new2']])
    isolated_settings.sync()

    win = main_window()
    assert win._cards_widget.card_list == [
        ('/old1', '/new1'), ('/old2', '/new2')]
    # Legacy key removed, new key written.
    assert not isolated_settings.contains(persistence.LEGACY_CARDS_KEY)
    assert isolated_settings.contains(persistence.CARDS_KEY)


def test_legacy_source_target_migrated(main_window, isolated_settings):
    isolated_settings.setValue(persistence.LEGACY_SOURCE_KEY, '/src')
    isolated_settings.setValue(persistence.LEGACY_TARGET_KEY, '/tgt')
    isolated_settings.sync()

    win = main_window()
    assert win._cards_widget.card_list == [('/src', '/tgt')]
    assert not isolated_settings.contains(persistence.LEGACY_SOURCE_KEY)
    assert not isolated_settings.contains(persistence.LEGACY_TARGET_KEY)


def test_save_then_reload(main_window, isolated_settings):
    win = main_window()
    win._cards_widget.card_list = [('/a', '/b')]  # added on top of seeded card
    win._save_settings()
    isolated_settings.sync()

    win2 = main_window()
    assert ('/a', '/b') in win2._cards_widget.card_list


# --- Start/Cancel button state machine ---------------------------------------

def test_start_enters_cancel_state(main_window, monkeypatch):
    win = main_window()
    # Don't actually launch the queue.
    monkeypatch.setattr(win, '_on_queue_setup', lambda: None)
    assert win._running is False
    assert win._copy_btn.text() == 'Start'

    win._on_copy_button()  # start
    assert win._running is True
    assert win._copy_btn.text() == 'Cancel'


def test_queue_stop_resets_button(main_window, monkeypatch):
    win = main_window()
    monkeypatch.setattr(win, '_on_queue_setup', lambda: None)
    win._on_copy_button()  # Start -> Cancel
    win._on_queue_stop()   # normal completion path
    assert win._running is False
    assert win._copy_btn.text() == 'Start'


def test_non_executable_prescript_does_not_stick_on_cancel(
        main_window, isolated_settings, tmp_path):
    # Regression for the "stuck on Cancel" bug: a non-executable prescript must
    # leave the button back at Start, not wedged on Cancel.
    script = tmp_path / 'prescript.sh'
    script.write_text('#!/bin/sh\necho hi\n')
    script.chmod(0o644)  # readable but NOT executable
    isolated_settings.setValue('prescript', str(script))
    isolated_settings.sync()

    win = main_window()
    win._on_copy_button()  # start -> hits the non-executable branch
    assert win._running is False
    assert win._copy_btn.text() == 'Start'


# --- exit code handling (via the pure classifier the GUI uses) ---------------

def test_exit_code_8_is_failure_not_success():
    from copy_tool import rclone
    assert rclone.classify_exit_code(8) == 'error'
