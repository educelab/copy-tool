@echo off
rem Dev launcher: runs CopyTool from a source checkout using the repo's venv.
set REPO_DIR=%~dp0..
set PYTHONPATH=%REPO_DIR%;%PYTHONPATH%
"%REPO_DIR%\venv\Scripts\python.exe" "%REPO_DIR%\copy_tool\main.py"
pause
