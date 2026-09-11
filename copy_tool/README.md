# EduceLab CopyTool

A GUI for copying data across filesystems using **rclone**.

## Installation
### Source
1. Set up a Python virtual environment:
   ```shell
   python -m venv venv
   source venv/bin/activate
   ```

2. Install the dependencies from the requirements file:
   ```shell
   python -m pip install -r requirements.txt
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

1. Follow the [source installation](#Source) instructions

2. Run `pyinstaller`:
   ```shell
   # macOS
   pyinstaller copy_tool/copy_tool_macOS.spec
   
   # Windows
   pyinstaller copy_tool\copy_tool_Windows.spec
   
   # Ubuntu
   pyinstaller copy_tool/copy_tool_Ubuntu.spec
   ```
