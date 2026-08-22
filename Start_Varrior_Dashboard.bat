@echo off
setlocal EnableExtensions EnableDelayedExpansion

title Varrior Labs FX Analytics Launcher
color 0A

rem ================================================================
rem Optional: if MetaTrader 5 is installed in a non-standard folder,
rem paste its full path between the quotes below.
rem Example:
rem set "CUSTOM_MT5_EXE=C:\Program Files\MetaTrader 5\terminal64.exe"
rem ================================================================
set "CUSTOM_MT5_EXE="

set "PROJECT_DIR=%~dp0"
if "%PROJECT_DIR:~-1%"=="\" set "PROJECT_DIR=%PROJECT_DIR:~0,-1%"

echo.
echo [1/6] Project: %PROJECT_DIR%
cd /d "%PROJECT_DIR%" || goto :fatal_project

rem --- Locate or create the project-local Python environment ----------
set "VENV_DIR=%PROJECT_DIR%\.venv"
set "PYTHON_EXE=%VENV_DIR%\Scripts\python.exe"
set "ENV_CREATED=0"

if exist "%PYTHON_EXE%" goto :python_ready

echo [2/6] Creating Python virtual environment...
where py >nul 2>&1
if not errorlevel 1 (
    py -3.11 -m venv "%VENV_DIR%" >nul 2>&1
    if not exist "%PYTHON_EXE%" py -3 -m venv "%VENV_DIR%"
) else (
    where python >nul 2>&1 || goto :fatal_python
    python -m venv "%VENV_DIR%"
)

if not exist "%PYTHON_EXE%" goto :fatal_venv
set "ENV_CREATED=1"

:python_ready
echo [2/6] Python: %PYTHON_EXE%

rem --- Install dependencies only when required ------------------------
set "NEED_INSTALL=%ENV_CREATED%"
"%PYTHON_EXE%" -c "import streamlit" >nul 2>&1
if errorlevel 1 set "NEED_INSTALL=1"

if "%NEED_INSTALL%"=="1" (
    echo [3/6] Installing dashboard dependencies. First launch may take a few minutes...
    "%PYTHON_EXE%" -m pip install --upgrade pip || goto :fatal_dependencies
    if exist "%PROJECT_DIR%\requirements.txt" (
        "%PYTHON_EXE%" -m pip install -r "%PROJECT_DIR%\requirements.txt" || goto :fatal_dependencies
    ) else (
        "%PYTHON_EXE%" -m pip install streamlit pandas plotly pyarrow || goto :fatal_dependencies
    )
    "%PYTHON_EXE%" -c "import streamlit" >nul 2>&1
    if errorlevel 1 "%PYTHON_EXE%" -m pip install streamlit pandas plotly pyarrow || goto :fatal_dependencies
) else (
    echo [3/6] Dashboard dependencies are ready.
)

rem --- Locate the Streamlit entry point -------------------------------
set "DASHBOARD_FILE=%PROJECT_DIR%\dashboard\app.py"
set "VARRIOR_DASHBOARD_CONFIG=%PROJECT_DIR%\config\local\dashboard_paths.json"

if exist "%DASHBOARD_FILE%" goto :dashboard_found
for %%F in (
    "%PROJECT_DIR%\dashboard\app.py"
    "%PROJECT_DIR%\dashboard.py"
    "%PROJECT_DIR%\streamlit_app.py"
    "%PROJECT_DIR%\app.py"
    "%PROJECT_DIR%\ui\dashboard.py"
) do (
    if exist "%%~F" (
        findstr /i /c:"streamlit" "%%~F" >nul 2>&1
        if not errorlevel 1 (
            set "DASHBOARD_FILE=%%~F"
            goto :dashboard_found
        )
    )
)

for /f "delims=" %%F in ('findstr /s /m /i /c:"import streamlit" "%PROJECT_DIR%\*.py" 2^>nul') do (
    set "DASHBOARD_FILE=%%F"
    goto :dashboard_found
)

goto :fatal_dashboard

:dashboard_found
echo [4/6] Dashboard: %DASHBOARD_FILE%
echo       Local artifact config: %VARRIOR_DASHBOARD_CONFIG%

rem --- Locate and start MetaTrader 5 when available -------------------
set "MT5_EXE="
if defined CUSTOM_MT5_EXE if exist "%CUSTOM_MT5_EXE%" set "MT5_EXE=%CUSTOM_MT5_EXE%"

if not defined MT5_EXE if exist "C:\Program Files\MetaTrader 5\terminal64.exe" set "MT5_EXE=C:\Program Files\MetaTrader 5\terminal64.exe"
if not defined MT5_EXE if exist "C:\Program Files (x86)\MetaTrader 5\terminal64.exe" set "MT5_EXE=C:\Program Files (x86)\MetaTrader 5\terminal64.exe"

if not defined MT5_EXE (
    for /f "delims=" %%F in ('where terminal64.exe 2^>nul') do (
        set "MT5_EXE=%%F"
        goto :mt5_found
    )
)

if not defined MT5_EXE if exist "%ProgramFiles%" (
    for /f "delims=" %%F in ('where /r "%ProgramFiles%" terminal64.exe 2^>nul') do (
        set "MT5_EXE=%%F"
        goto :mt5_found
    )
)

:mt5_found
tasklist /fi "imagename eq terminal64.exe" 2>nul | find /i "terminal64.exe" >nul
if not errorlevel 1 (
    echo [5/6] MetaTrader 5 is already running.
) else if defined MT5_EXE (
    echo [5/6] Starting MetaTrader 5: %MT5_EXE%
    start "MetaTrader 5" "%MT5_EXE%"
    timeout /t 4 /nobreak >nul
) else (
    echo [5/6] WARNING: terminal64.exe was not found.
    echo       Dashboard will still start. To auto-start MT5, edit this BAT
    echo       and set CUSTOM_MT5_EXE near the top of the file.
)

rem --- Start browser shortly after the Streamlit server begins --------
set "DASHBOARD_PORT=8501"
netstat -ano | findstr /r /c:":8501 .*LISTENING" >nul 2>&1
if not errorlevel 1 set "DASHBOARD_PORT=8502"
echo [6/6] Starting dashboard at http://localhost:%DASHBOARD_PORT%
echo.
echo Keep this window open while using the dashboard.
echo Press Ctrl+C to stop it.
echo.

start "" powershell.exe -NoProfile -WindowStyle Hidden -Command "Start-Sleep -Seconds 4; Start-Process 'http://localhost:%DASHBOARD_PORT%'"

"%PYTHON_EXE%" -m streamlit run "%DASHBOARD_FILE%" --server.port %DASHBOARD_PORT% --server.headless true --browser.gatherUsageStats false
set "DASHBOARD_EXIT=%ERRORLEVEL%"

echo.
echo Dashboard stopped with exit code %DASHBOARD_EXIT%.
pause
exit /b %DASHBOARD_EXIT%

:fatal_project
echo ERROR: Could not open the project directory.
goto :fatal

:fatal_python
echo ERROR: Python was not found. Install Python 3.11 and enable the Python launcher.
goto :fatal

:fatal_venv
echo ERROR: Could not create .venv.
goto :fatal

:fatal_dependencies
echo ERROR: Could not install Python dependencies. Check the messages above.
goto :fatal

:fatal_dashboard
echo ERROR: No Streamlit dashboard file was found inside:
echo        %PROJECT_DIR%
echo.
echo Ask Codex to report the exact Streamlit entry-point path.
goto :fatal

:fatal
echo.
pause
exit /b 1
