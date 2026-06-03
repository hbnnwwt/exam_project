@echo off
chcp 65001 >nul 2>&1
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo ========================================
echo   Exam Project - GUI
echo ========================================
echo.

set "PYTHON_CMD="

if exist "python_portable\python.exe" (
    set "PYTHON_CMD=python_portable\python.exe"
) else (
    py --version >nul 2>&1
    if !errorlevel! equ 0 (
        set "PYTHON_CMD=py"
    ) else (
        python --version >nul 2>&1
        if !errorlevel! equ 0 (
            set "PYTHON_CMD=python"
        ) else (
            echo [Error] Python not found.
            echo   Please run setup.bat first, or install Python 3.8+.
            echo.
            pause
            exit /b 1
        )
    )
)

echo [Using] !PYTHON_CMD!
echo.

set "PYTHONPATH=%CD%\src;%PYTHONPATH%"

"!PYTHON_CMD!" -X utf8 -m streamlit --version >nul 2>&1
if !errorlevel! neq 0 (
    echo [Error] Streamlit not found.
    echo   Run setup.bat first to install dependencies.
    echo.
    pause
    exit /b 1
)

set "PORT=8501"
set "PORT_AVAILABLE=0"

netstat -ano | findstr :%PORT% >nul 2>&1
if !errorlevel! equ 0 (
    for /f "tokens=5" %%a in ('netstat -ano ^| findstr :%PORT%') do (
        echo [Warning] Port %PORT% is occupied by PID %%a
    )
    echo   Searching for available port...

    for /l %%p in (8502, 1, 8510) do (
        if !PORT_AVAILABLE! equ 0 (
            netstat -ano | findstr :%%p >nul 2>&1
            if !errorlevel! neq 0 (
                set "PORT=%%p"
                set "PORT_AVAILABLE=1"
            )
        )
    )

    if !PORT_AVAILABLE! equ 0 (
        echo [Error] No available port found between 8502-8510.
        echo   Please close other Streamlit instances manually.
        echo.
        pause
        exit /b 1
    )
    echo [Info] Auto-switched to port !PORT!
) else (
    echo [Info] Port %PORT% is available.
)

echo [Launching] Streamlit GUI on port !PORT!...
echo   URL: http://localhost:!PORT!
echo.

"!PYTHON_CMD!" -X utf8 -m streamlit run app.py --server.port !PORT!

if !errorlevel! neq 0 (
    echo.
    echo [Error] Failed to start Streamlit.
    echo   Run setup.bat first to install dependencies.
    echo.
)

pause
