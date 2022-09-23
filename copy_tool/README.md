# EduceLab CopyTool

A GUI for copying data across filesystems using **rclone**.

## Installation

1. Set up a Python virtual environment:
   ```shell
   python -m venv venv
   source venv/bin/activate
   ```

2. Install the dependencies from the requirements file:
   ```
   python -m pip install -r requirements.txt
   ```

3. Install rclone and make it accessible to the system PATH: https://rclone.org/install/

4. Run the application
   ```shell
   python copy_tool/main.py
   ```
   
## Building a deployable app package

1. Follow the [Installation](#Installation) instructions

2. Run `pyinstaller`:
   ```shell
   # macOS
   pyinstaller copy_tool/copy_tool_macOS.spec
   
   # Windows
   pyinstaller copy_tool\copy_tool_Windows.spec
   ```
