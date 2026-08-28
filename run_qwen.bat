@echo off
setlocal enabledelayedexpansion
title Agent Flow - Qwen 2.5 Coder ^& llama.cpp Runner

cd /d "%~dp0"

echo =======================================================
echo   AGENT FLOW: Qwen 2.5 Coder 3B + llama.cpp Runner
echo =======================================================
echo.

set "MODEL_PATH=C:\models\qwen2.5-coder-3b-instruct-q4_k_m.gguf"
set "SERVER_EXE=tools\llama.cpp\llama-server.exe"
set "PYTHON_EXE=.venv\Scripts\python.exe"

if not "%~1"=="" (
    set "TOPIC=%~1"
) else (
    set "TOPIC=AI, quantum mechanics, defence systems, theoretical physics"
)

:: 1. Check Python virtual environment
if not exist "%PYTHON_EXE%" (
    echo [ERROR] Virtual environment not found at .venv\Scripts\python.exe
    echo Please create the virtual environment first.
    pause
    exit /b 1
)

:: 2. Check if llama-server is listening on port 8080
echo [1/3] Checking llama.cpp server on port 8080...
powershell -NoProfile -Command "try { $null = Invoke-RestMethod -Uri 'http://127.0.0.1:8080/v1/models' -TimeoutSec 2 -ErrorAction Stop; exit 0 } catch { exit 1 }"
if %ERRORLEVEL% NEQ 0 (
    echo [*] llama-server is not running. Starting server...
    if not exist "%SERVER_EXE%" (
        echo [ERROR] llama-server.exe not found at %SERVER_EXE%
        pause
        exit /b 1
    )
    if not exist "%MODEL_PATH%" (
        echo [WARNING] Model file not found at %MODEL_PATH%
        echo Searching for any .gguf file...
        for /r %%F in (*.gguf) do (
            set "MODEL_PATH=%%F"
            goto :found_model
        )
        echo [ERROR] No GGUF model file found. Please specify the path in this script.
        pause
        exit /b 1
    )
    :found_model
    echo [*] Using model: !MODEL_PATH!
    start "llama-server" /min "%SERVER_EXE%" -m "!MODEL_PATH!" -c 2048 --port 8080 --threads 4
    
    echo [*] Waiting for llama-server to initialize...
    powershell -NoProfile -Command "$ready = $false; for ($i=0; $i -lt 30; $i++) { try { $null = Invoke-RestMethod -Uri 'http://127.0.0.1:8080/v1/models' -TimeoutSec 1 -ErrorAction Stop; $ready = $true; break } catch { Start-Sleep -Seconds 1 } }; if (-not $ready) { exit 1 }"
    if %ERRORLEVEL% NEQ 0 (
        echo [ERROR] llama-server failed to start within 30 seconds.
        pause
        exit /b 1
    )
)
echo [OK] llama.cpp server is ready!
echo.

:: 3. Launch Qwen Autonomous Agent
echo [2/3] Running Qwen Autonomous Harness...
echo [*] Topic: %TOPIC%
echo.

"%PYTHON_EXE%" -m local_news_agent.cli qwen-run --browser direct --topic "%TOPIC%"
set "EXIT_CODE=%ERRORLEVEL%"

echo.
echo =======================================================
if %EXIT_CODE% EQU 0 (
    echo [SUCCESS] Qwen run completed successfully!
) else (
    echo [EXIT] Finished with exit code: %EXIT_CODE%
)
echo =======================================================
echo.

pause
