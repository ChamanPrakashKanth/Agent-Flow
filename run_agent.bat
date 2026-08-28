@echo off
setlocal
title Agent Flow Runner

cd /d "%~dp0"

set "PYTHON_EXE=.venv\Scripts\python.exe"

if not exist "%PYTHON_EXE%" (
    echo [ERROR] Python environment not found at .venv\Scripts\python.exe
    pause
    exit /b 1
)

if "%~1"=="" goto :menu
"%PYTHON_EXE%" -m local_news_agent.cli %*
goto :done

:menu
echo =======================================================
echo                 AGENT FLOW CONTROL MENU
echo =======================================================
echo  1. Run Qwen 2.5 Coder + llama.cpp Harness
echo  2. Run Standard News Agent Pipeline (run)
echo  3. Run Health / Environment Doctor
echo  4. Run Benchmark Test Suite (30 tasks)
echo  5. Publish Due Drafts (Review Queue)
echo  6. Exit
echo =======================================================
set /p "CHOICE=Select an option (1-6): "

if "%CHOICE%"=="1" (
    call run_qwen.bat
    goto :done
)
if "%CHOICE%"=="2" (
    "%PYTHON_EXE%" -m local_news_agent.cli run
    pause
    goto :done
)
if "%CHOICE%"=="3" (
    "%PYTHON_EXE%" -m local_news_agent.cli doctor
    pause
    goto :done
)
if "%CHOICE%"=="4" (
    "%PYTHON_EXE%" -m local_news_agent.cli benchmark
    pause
    goto :done
)
if "%CHOICE%"=="5" (
    "%PYTHON_EXE%" -m local_news_agent.cli publish-due
    pause
    goto :done
)

:done
