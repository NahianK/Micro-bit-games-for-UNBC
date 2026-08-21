@echo off
cd /d "%~dp0"
echo Installing dependencies...
pip install -r requirements.txt --quiet
echo Starting Quest Engine...
python app.py
pause
