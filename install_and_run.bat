@echo off
chcp 65001 >nul

echo [1/2] 패키지 설치 중...
python -m pip install -r requirements.txt

echo.
echo [2/2] 서버 시작 (포트 5002)...
python app.py

pause
