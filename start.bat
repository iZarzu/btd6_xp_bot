@echo off
REM Creates a local Python environment (.venv) on the first run, installs the requirements
REM and starts the bot. Extra arguments are passed through, e.g.: start.bat run strategies\infernal_deflation.yaml
REM PL: Przy pierwszym uruchomieniu tworzy lokalne srodowisko Pythona (.venv), instaluje biblioteki
REM i uruchamia bota. Dodatkowe argumenty sa przekazywane dalej.
setlocal
cd /d "%~dp0"

if exist ".venv\installed.txt" goto run

if not exist ".venv\Scripts\python.exe" (
    echo Creating Python environment / Tworze srodowisko Pythona...
    py -3 -m venv .venv 2>nul
    if not exist ".venv\Scripts\python.exe" python -m venv .venv
    if not exist ".venv\Scripts\python.exe" goto nopython
)

echo Installing requirements / Instaluje biblioteki...
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto failed
echo ok> ".venv\installed.txt"

:run
".venv\Scripts\python.exe" -m btd6bot %*
if errorlevel 1 pause
goto :eof

:nopython
echo.
echo Python not found. Install it from https://www.python.org (tick "Add Python to PATH").
echo PL: Nie znaleziono Pythona. Zainstaluj go z https://www.python.org (zaznacz "Add Python to PATH").
pause
goto :eof

:failed
echo.
echo Installing requirements failed - see the errors above.
echo PL: Instalacja bibliotek nie powiodla sie - zobacz bledy powyzej.
pause
