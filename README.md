# EduceLab CopyTool

A GUI for copying data across filesystems using **rclone**.

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

Packages for all supported platforms are also built by the
[build workflow](.github/workflows/build.yml) on every push and are available
as workflow artifacts.

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
