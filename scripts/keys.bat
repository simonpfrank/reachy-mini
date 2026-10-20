@echo off
rem Manage the robot tools API keys on Windows (Credential Manager). Same commands as scripts/keys.sh:
rem   scripts\keys.bat add NAME ^| remove NAME ^| check NAME
setlocal
set "ROOT=%~dp0.."
set "PYTHON=%ROOT%\.venv\Scripts\python.exe"
if not exist "%PYTHON%" (
    echo No project .venv: create it first ^(docs\development_setup.md^). 1>&2
    exit /b 1
)
"%PYTHON%" "%ROOT%\robot_tools\reachy_lib\keys.py" %*
exit /b %ERRORLEVEL%
