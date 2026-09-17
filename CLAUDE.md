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

### Versioning and release

`copy_tool/_version.py` is the single source of truth. `pyproject.toml` reads
it via `[tool.setuptools.dynamic] version = { attr = ... }` and `main()` passes
it to `setApplicationVersion`, so there is exactly one place to bump. Keep the
file to plain string literals: setuptools parses it with `ast` rather than
importing the package, which is what keeps it dependency-free.

CI rewrites that file before `pip install`, so a binary reports the commit it
was built from. The version job in `build.yml` resolves the string:

| Trigger | Version | Published as |
| --- | --- | --- |
| push to `main` | `1.3.0+edge.gabc12345` | rolling `edge` prerelease |
| push of tag `v1.3.0` | `1.3.0` | release `v1.3.0` |
| pull request | `1.3.0+dev.gabc12345` | nothing |

The short hash is `g`-prefixed because PEP 440 treats an all-numeric local
segment as a number and strips its leading zeros, which would silently corrupt
a hash like `0012345`. `tests/test_version.py` guards this. The hash width is
pinned with `--short=8` because `core.abbrev` is length-adaptive.

To cut a release: bump `_version.py`, commit, then tag `v<same version>`. The
version job fails the build if the tag and the file disagree.

Release assets have constant filenames so the `releases/latest/download/...`
and `releases/download/edge/...` URLs in the README stay valid. Renaming one
breaks published links.

### Build workflow wiring

`build.yml` triggers on `workflow_run` from `Test`, so nothing publishes from a
red commit. That trigger has sharp edges, all handled in the `version` job:

- The workflow file always executes from the default branch, so changes to
  `build.yml` cannot be tested in a PR. `pull_request` is a separate trigger
  that builds (but never publishes) so PRs still exercise the build itself.
- `github.ref` and `github.sha` point at the default branch, *not* at the
  triggering commit. Every job checks out `needs.version.outputs.sha`, taken
  from `workflow_run.head_sha`. Never use `github.sha` in this workflow.
- `github.ref` cannot be used to detect a tag either. The channel comes from
  `workflow_run.head_branch`, which carries the tag name on a tag push, and is
  confirmed against a real ref before being trusted.
- `test.yml` must keep its `tags: ["v*"]` trigger. Without it a tag push runs
  no tests, fires no `workflow_run`, and publishes nothing, silently.
- `workflow_run` also fires for PR and topic-branch test runs. Those set
  `build=false` so the `pull_request` trigger does not build twice.

`publish` needs all four build jobs, so a release never contains a mix of old
and new platforms.

Rolling `edge` is updated in place, never deleted. `target_commitish` is
documented as "unused if the Git tag already exists", so a republish has to
force-move `refs/tags/edge` via the git refs API or `edge` stays pinned to the
commit that first created it. Deleting the release instead would work, but a
failed asset upload then leaves no `edge` at all; updating in place degrades to
serving the previous commit's binaries. Uploads are retried because the upload
endpoint intermittently returns HTTP 500 on assets this size.

Order matters: assets upload *before* the tag moves and the title is rewritten.
Relabelling first would leave a failed run advertising a commit whose binaries
never landed, which is worse than a stale release.

## Constraints

- The macOS job is pinned to `macos-26` (arm64), not `macos-latest`, for the
  same reason the Ubuntu jobs run in containers: the deployment floor should
  not drift with the runner image. There is no Intel Mac build.
- Packages are unsigned on both macOS and Windows. Gatekeeper and SmartScreen
  block them on first launch; the README documents the workaround. Adding
  signing means an Apple Developer account plus notarization in the macOS job.
- CI tests run on Python 3.9–3.13, but the legacy Ubuntu 20.04 build job
  installs the package on Python **3.8** with `--ignore-requires-python`.
  Shipped code must stay 3.8-compatible: use `typing.List`/`Dict`/`Union`
  rather than PEP 585/604 syntax. See `requirements-legacy.txt` for why that
  job pins `PySide6<6.7`.
