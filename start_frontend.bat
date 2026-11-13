@echo off
cd /d "C:\Users\Vishnu\Downloads\Hackthon\frontend"
set "PATH=C:\Users\Vishnu\AppData\Local\Programs\nodejs;%PATH%"
echo Starting Distill Frontend (Next.js on http://localhost:3000)...
call npm run dev
pause
