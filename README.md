# EduceLab CopyTool

A GUI for copying data across filesystems using **rclone**.

## Download

Prebuilt packages are published to
[Releases](https://github.com/educelab/copy-tool/releases). Every link below is permanent.

| Platform | Latest release | Edge |
| --- | --- | --- |
| macOS (Apple Silicon) | [download](https://github.com/educelab/copy-tool/releases/latest/download/CopyTool-macos-arm64.dmg) | [download](https://github.com/educelab/copy-tool/releases/download/edge/CopyTool-macos-arm64.dmg) |
| Windows | [download](https://github.com/educelab/copy-tool/releases/latest/download/CopyTool-windows.exe) | [download](https://github.com/educelab/copy-tool/releases/download/edge/CopyTool-windows.exe) |
| Ubuntu 22.04+ | [download](https://github.com/educelab/copy-tool/releases/latest/download/CopyTool-ubuntu-22.04.tar.gz) | [download](https://github.com/educelab/copy-tool/releases/download/edge/CopyTool-ubuntu-22.04.tar.gz) |
| Ubuntu 20.04 (legacy) | [download](https://github.com/educelab/copy-tool/releases/latest/download/CopyTool-ubuntu-20.04-legacy.tar.gz) | [download](https://github.com/educelab/copy-tool/releases/download/edge/CopyTool-ubuntu-20.04-legacy.tar.gz) |

**Edge** is a rolling prerelease rebuilt from every commit to `main`. It is
replaced on each push, so it is unstable by design and there is no way to get
an older one. Use the latest release unless you need an unreleased fix.

There is no Intel Mac build.

### Which build am I running?

The version is the first line of the console pane and of every log file, so
please include it in bug reports. An edge build reports a commit, e.g.
`v1.3.0+edge.g0be1b355`; run `git show 0be1b355` to see exactly what it
contains.

| Platform | Log file |
| --- | --- |
| macOS | `~/Library/Application Support/EduceLab/CopyTool/logs/CopyTool_log.txt` |
| Windows | `%LOCALAPPDATA%\EduceLab\CopyTool\logs\CopyTool_log.txt` |
| Linux | `~/.local/share/EduceLab/CopyTool/logs/CopyTool_log.txt` |

### First launch

The packages are not code-signed, so both macOS and Windows will refuse to open
them until you say otherwise. This is expected.

On macOS, open the disk image, drag **CopyTool** onto the **Applications**
alias, and then clear the quarantine flag the browser set:

```shell
xattr -dr com.apple.quarantine /Applications/CopyTool.app
```

Alternatively, right-click the app, choose **Open**, and confirm at the prompt.

On Windows, SmartScreen shows "Windows protected your PC". Click **More info**
and then **Run anyway**.

## Installation
### Source
1. Set up a Python virtual environment:
   ```shell
   python -m venv venv
   source venv/bin/activate
   ```

2. Install the project and its dependencies:
   ```shell
   python -m pip install -e .
   ```
   
3. **(Ubuntu only)** Install the PySide6 and pyinstaller system dependencies
   ```shell
   sudo apt install binutils libgl-dev libglib2.0-dev qt6-base-dev
   ```

4. Install rclone and make it accessible to the system PATH: https://rclone.org/install/

5. Run the application
   ```shell
   python copy_tool/main.py
   ```
   
### Building a deployable app package

1. Follow the [source installation](#source) instructions

2. Run `pyinstaller`:
   ```shell
   # macOS
   pyinstaller copy_tool/copy_tool_macOS.spec
   
   # Windows
   pyinstaller copy_tool\copy_tool_Windows.spec
   
   # Ubuntu
   pyinstaller copy_tool/copy_tool_Ubuntu.spec
   ```

The [build workflow](.github/workflows/build.yml) builds all four packages on
every pull request, and publishes them to [Releases](#download) once the test
suite passes on `main` or on a `v*` tag.

## Tests

```shell
python -m pip install -e .[test]
pytest
```

Qt runs headless (`QT_QPA_PLATFORM=offscreen`, set in `tests/conftest.py`), so
the GUI tests need no display. Tests that require PySide6 or pytest-qt skip
themselves when those packages are missing.

## License

Copyright (C) 2026 EduceLab, University of Kentucky

This program is free software: you can redistribute it and/or modify it under
the terms of the GNU General Public License as published by the Free Software
Foundation, either version 3 of the License, or (at your option) any later
version.

This program is distributed in the hope that it will be useful, but WITHOUT ANY
WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A
PARTICULAR PURPOSE. See the [GNU General Public License](LICENSE) for more
details.
