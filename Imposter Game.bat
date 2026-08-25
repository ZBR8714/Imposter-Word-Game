@echo off
setlocal
cd /d "%~dp0"

rem =============================================================================
rem  Imposter Word Game launcher
rem  - Checks that Python (with its bundled Tkinter GUI toolkit) is installed.
rem  - No third-party packages are needed: the game only uses Python's built-in
rem    standard library (json, random, shutil, tkinter, pathlib), so there is
rem    nothing to "pip install".
rem  - Then runs imposter_game.py, which must sit in this same folder.
rem =============================================================================

set "PYEXE="

where pythonw >nul 2>nul && set "PYEXE=pythonw"

if not defined PYEXE (
    where python >nul 2>nul && set "PYEXE=python"
)

if not defined PYEXE (
    py -3 -c "1" >nul 2>nul && set "PYEXE=py -3"
)

if not defined PYEXE (
    echo.
    echo  Python was not found on this computer.
    echo.
    echo  Opening the Python download page - please install it, and make sure to
    echo  tick "Add python.exe to PATH" on the first setup screen. Once installed,
    echo  double-click this file again.
    echo.
    start "" "https://www.python.org/downloads/"
    pause
    exit /b 1
)

%PYEXE% -c "import tkinter" >nul 2>nul
if errorlevel 1 (
    echo.
    echo  Python is installed, but it's missing Tkinter ^(the toolkit this game's
    echo  window is built with^). This usually happens with a custom/minimal
    echo  Python install.
    echo.
    echo  Please reinstall Python from python.org and make sure "tcl/tk and IDLE"
    echo  is checked during setup, then run this file again.
    echo.
    start "" "https://www.python.org/downloads/"
    pause
    exit /b 1
)

if not exist "%~dp0imposter_game.py" (
    echo.
    echo  Could not find imposter_game.py in this folder:
    echo    %~dp0
    echo  Make sure the .bat and the .py file are in the same folder.
    echo.
    pause
    exit /b 1
)

start "" %PYEXE% "%~dp0imposter_game.py"