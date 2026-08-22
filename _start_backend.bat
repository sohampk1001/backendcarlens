@echo off
cd /d "D:\trae projects\CARVIEW_AI\backend"
venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000 > uvicorn.log 2>&1
