@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo ========================================
echo   Exam Project - Environment Setup
echo ========================================
echo.

set "PYTHON_DIR=%~dp0python_portable"
set "PYTHON_EXE=%PYTHON_DIR%\python.exe"

REM ---- 1. Use or download portable Python -------------------------------
if exist "%PYTHON_EXE%" (
    echo [Info] Portable Python found, skipping download.
    goto :install_deps
)

echo [Download] Python 3.12 portable ...
echo.

set "PYTHON_VERSION=3.12.4"
set "PYTHON_ZIP=python-%PYTHON_VERSION%-embed-amd64.zip"
set "DOWNLOAD_URL=https://www.python.org/ftp/python/%PYTHON_VERSION%/%PYTHON_ZIP%"

powershell -Command "& { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri '%DOWNLOAD_URL%' -OutFile '%~dp0%PYTHON_ZIP%' -UseBasicParsing }" 2>nul
if !errorlevel! neq 0 (
    echo [Error] Download failed. Please check your internet connection.
    pause
    exit /b 1
)

echo [Extract] Python ...
if exist "%PYTHON_DIR%" rmdir /s /q "%PYTHON_DIR%"
mkdir "%PYTHON_DIR%"
powershell -Command "Expand-Archive -Path '%~dp0%PYTHON_ZIP%' -DestinationPath '%PYTHON_DIR%' -Force"
del "%~dp0%PYTHON_ZIP%" 2>nul

if not exist "%PYTHON_EXE%" (
    echo [Error] Failed to extract Python.
    pause
    exit /b 1
)

REM Enable site-packages for embed version
set "PTH_FILE=%PYTHON_DIR%\python312._pth"
if exist "!PTH_FILE!" (
    echo import site>> "!PTH_FILE!"
)

REM Install pip
echo [Install] pip ...
powershell -Command "& { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri 'https://bootstrap.pypa.io/get-pip.py' -OutFile '%PYTHON_DIR%\get-pip.py' -UseBasicParsing }" 2>nul
if exist "%PYTHON_DIR%\get-pip.py" (
    "%PYTHON_EXE%" "%PYTHON_DIR%\get-pip.py" --no-warn-script-location -i https://pypi.tuna.tsinghua.edu.cn/simple --trusted-host pypi.tuna.tsinghua.edu.cn
    del "%PYTHON_DIR%\get-pip.py" 2>nul
)

if not exist "%PYTHON_DIR%\Scripts\pip.exe" (
    echo [Error] Failed to install pip.
    pause
    exit /b 1
)

echo [OK] Python installed.
echo.

REM ---- 2. Install dependencies -------------------------------------------
:install_deps
echo [Install] Dependencies ...
echo.

set "PYTHONPATH=%~dp0src"

"%PYTHON_EXE%" -m pip install --upgrade pip -i https://pypi.tuna.tsinghua.edu.cn/simple --trusted-host pypi.tuna.tsinghua.edu.cn >nul 2>&1
"%PYTHON_EXE%" -m pip install setuptools wheel -i https://pypi.tuna.tsinghua.edu.cn/simple --trusted-host pypi.tuna.tsinghua.edu.cn >nul 2>&1
"%PYTHON_EXE%" -m pip install -r "%~dp0requirements.txt" -i https://pypi.tuna.tsinghua.edu.cn/simple --trusted-host pypi.tuna.tsinghua.edu.cn
if !errorlevel! neq 0 (
    echo [Error] Failed to install dependencies.
    pause
    exit /b 1
)

echo [Install] exam_project package (editable, no build isolation) ...
"%PYTHON_EXE%" -m pip install -e . --no-build-isolation -i https://pypi.tuna.tsinghua.edu.cn/simple --trusted-host pypi.tuna.tsinghua.edu.cn
if !errorlevel! neq 0 (
    echo.
    echo [Error] Failed to install exam_project package.
    echo   Try running the same command manually to see the real error:
    echo     "%PYTHON_EXE%" -m pip install -e . --no-build-isolation
    pause
    exit /b 1
)

echo.
echo ========================================
echo Setup completed successfully!
echo ========================================
echo.
echo Next step:
echo   Double-click run_gui.bat to launch the GUI
echo.
pause
