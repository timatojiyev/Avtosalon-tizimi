@echo off
REM Windows uchun bir martalik o'rnatish va ishga tushirish
cd /d "%~dp0"
if not exist .venv (
  echo [1/3] Virtual muhit yaratilmoqda...
  python -m venv .venv || goto :error
)
call .venv\Scripts\activate.bat
echo [2/3] Paketlar o'rnatilmoqda...
python -m pip install --upgrade pip >nul
pip install -r requirements-test.txt || goto :error
echo [3/3] Dastur ishga tushmoqda...
python run.py
goto :eof
:error
echo Xatolik yuz berdi. Python 3.10+ o'rnatilganini tekshiring.
pause
