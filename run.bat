@echo off
cd /d "%~dp0"
start http://127.0.0.1:5000
echo Website chal rahi hai. Browser mein http://127.0.0.1:5000 khulega. Band karne ke liye Ctrl+C
python app.py
pause
