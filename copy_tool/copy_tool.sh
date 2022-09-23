export PYTHONPATH=~/source/acquisition-workflow/:$PYTHONPATH
source ~/source/acquisition-workflow/venv/Scripts/activate
~/source/acquisition-workflow/venv/Scripts/python ~/source/acquisition-workflow/copy_tool/main.py

echo
echo "Press any key to exit..."
read