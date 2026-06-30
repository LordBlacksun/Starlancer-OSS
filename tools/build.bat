@echo off
REM ===========================================================================
REM build.bat - build StarlancerStudio.exe (one-file, windowed) with PyInstaller.
REM Builds OUR GUI only. It bundles the prebuilt XInput shim as data so the
REM Controller section can install it. It NEVER launches the game.
REM Run from the tools\ folder in any cmd.exe:  build.bat
REM ===========================================================================
setlocal
cd /d "%~dp0"

REM 1) Pick a Python (prefer the py launcher; fall back to PATH).
set "PY=python"
where py >nul 2>nul && set "PY=py -3"

REM 2) Dependencies: customtkinter (only runtime dep) + PyInstaller.
%PY% -m pip install --upgrade customtkinter pyinstaller

REM 3) Clean previous artifacts.
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist StarlancerStudio.spec del /q StarlancerStudio.spec

REM 4) Build.
REM    --collect-all customtkinter  bundles its Tcl theme JSON (REQUIRED, else the
REM                                 one-file exe crashes at startup).
REM    --add-data ships the prebuilt XInput shim; read from sys._MEIPASS at runtime.
%PY% -m PyInstaller ^
  --onefile ^
  --windowed ^
  --name StarlancerStudio ^
  --icon "assets\app.ico" ^
  --collect-all customtkinter ^
  --hidden-import darkdetect ^
  --add-data "xinput_shim\dinput.dll;xinput_shim" ^
  --add-data "xinput_shim\xinput_shim.ini;xinput_shim" ^
  --add-data "assets\blank.bik;assets" ^
  --add-data "assets\app.ico;assets" ^
  slstudio_app.py

echo.
echo Done. Output: dist\StarlancerStudio.exe
endlocal
