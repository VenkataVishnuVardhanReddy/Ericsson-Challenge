@echo off
cd /d "C:\Users\Vishnu\Downloads\Hackthon"
echo Starting Distill Backend (FastAPI on http://localhost:8000)...
call .venv\Scripts\python.exe -m uvicorn distill.app:app --port 8000
pause
