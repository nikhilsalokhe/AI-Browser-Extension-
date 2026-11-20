@echo off
set PYTHONDONTWRITEBYTECODE=1
title AI Browser Agent
echo Starting AI Browser Agent (Python Edition)...
python -B app.py
if errorlevel 1 (
    echo.
    echo GUI launch error. Running CLI version...
    python -B agent.py
    pause
)
