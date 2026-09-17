# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

EduceLab CopyTool: a PySide6 desktop GUI that drives the `rclone` CLI to copy
data across filesystems. `rclone` must be on PATH to run from source.

## Commands

```shell
# Setup (Ubuntu also needs: sudo apt install binutils libgl-dev libglib2.0-dev qt6-base-dev)
python -m venv venv && source venv/bin/activate
python -m pip install -e '.[test]'

# Run from source
python copy_tool/main.py          # or the copy_tool/copy_tool.sh / .bat dev launchers

# Tests (headless; QT_QPA_PLATFORM=offscreen is set in tests/conftest.py)
pytest
pytest tests/test_gui.py::test_first_launch_seeds_one_card
pytest tests/test_rclone.py -k classify

# Package
pyinstaller copy_tool/copy_tool_macOS.spec     # _Windows.spec / _Ubuntu.spec
```

## Architecture

Four layers, split along a deliberate Qt boundary:

- `copy_tool/main.py` — `MainWindow` (queue orchestration, rclone process,
  console log), `SettingsWindow` (preferences dialog), logging setup, and the
  `main()` entry point.
- `copy_tool/widgets/widgets.py` — `CopyJobCard` and `CardListWidget`. Pure Qt
  view code with no knowledge of rclone or persistence.
- `copy_tool/rclone/rclone.py` — rclone log/progress regexes, exit-code
  classification, executable discovery, and argument building.
- `copy_tool/persistence.py` — settings serialization and legacy migration.

`rclone.py` and `persistence.py` import nothing from Qt so they can be unit
tested without a display or PySide6. Keep them that way.

### Transfer queue

The queue is an event-driven chain, not a loop: `_on_queue_start` → optional
prescript (`QProcess`) → `_on_queue_setup` snapshots the cards into
`self._queue` → the `advance_queue` signal pops one card and starts `rclone
copy` → `finished` classifies the exit code → emits `advance_queue` again.
An empty queue ends at `_on_queue_stop`.

Cancellation sets `_queue_canceled`, clears `_queue`, and terminates child
processes; every completion handler checks that flag first. The Start/Cancel
button has one persistent connection that branches on `self._running` —
swapping connections previously left the button stuck on "Cancel".

Progress comes from rclone's stderr: it runs with `--stats-one-line
--stats-log-level NOTICE`, and `parse_log_message` turns NOTICE lines into
either a message or a `PROGRESS` dict, whose units `bitmath` normalizes for the
progress bar.

rclone preferences (`--max-backlog`, `--stats`) live in module-level globals in
`rclone.py`, set from `QSettings` by `SettingsWindow` and read by
`default_args()`.

### Settings storage

`QSettings` under organization `EduceLab`, application `CopyTool`. Job cards are
stored as a *single JSON string* under `cards_json` plus a `settings_version`,
because the native backend reads an empty list back as `None` and a
one-element list back as the bare element — both of which used to crash
startup. Pre-1.3.0 stores (`cards`, `source`, `target`) are migrated and their
keys removed on first load. Each restore step is individually guarded so one
corrupt value cannot take down startup.

### Frozen vs. source paths

The PyInstaller specs bundle whatever `rclone` is on PATH at build time.
`rclone.executable_path()` and `app_icon_path()` both branch on
`sys._MEIPASS` to resolve bundled resources first, then fall back to the
source tree / system PATH. Anything new that loads an asset needs the same
treatment, and the asset must be listed in all three spec files.

## Constraints

- The version string is duplicated: `pyproject.toml` `version` and the
  `setApplicationVersion` call in `main()`. Bump both.
- CI tests run on Python 3.9–3.13, but the legacy Ubuntu 20.04 build job
  installs the package on Python **3.8** with `--ignore-requires-python`.
  Shipped code must stay 3.8-compatible: use `typing.List`/`Dict`/`Union`
  rather than PEP 585/604 syntax. See `requirements-legacy.txt` for why that
  job pins `PySide6<6.7`.
