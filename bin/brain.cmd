@echo off
rem brain: open your notes app on Windows. Close this window (or Ctrl+C) to stop it.
rem Env: BRAIN_NOTES (notes folder, default: the folder above this brain folder), BRAIN_PORT (default 4747)
setlocal
set "APP=%~dp0..\app"
if "%BRAIN_PORT%"=="" set "BRAIN_PORT=4747"
set "PY=python"
where py >nul 2>nul && set "PY=py -3"
if defined BRAIN_NOTES (
  %PY% "%APP%\server.py" --port %BRAIN_PORT% --notes "%BRAIN_NOTES%"
) else (
  %PY% "%APP%\server.py" --port %BRAIN_PORT%
)
