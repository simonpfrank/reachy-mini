@echo off
rem Run the Reachy hub dashboard in this window (Ctrl+C stops it). Settings come from the environment or .env.
setlocal
set "ROOT=%~dp0.."
set "PYTHON=%ROOT%\.venv\Scripts\python.exe"
if not exist "%PYTHON%" (
    echo No project .venv: create it first ^(docs\development_setup.md^). 1>&2
    exit /b 1
)
cd /d "%ROOT%"
"%PYTHON%" -m reachy_hub
exit /b %ERRORLEVEL%
