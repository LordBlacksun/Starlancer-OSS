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

REM 4) Optional bundled assets. Neither file is in the repo (*.dll / *.bik are
REM    git-ignored), so a fresh clone builds without them; PyInstaller would abort
REM    on a missing --add-data, hence the checks.
REM      xinput_shim\dinput.dll  build it first from tools\xinput_shim\ (its build.bat);
REM                              without it the Controller section cannot install the shim.
REM      assets\blank.bik        esc0rtd3w's black clip, if you want the real clip bundled;
REM                              without it the Boot Videos section uses its own generated
REM                              zero-frame clip (blank_boot_videos.make_blank_bik).
set EXTRA=
if exist "xinput_shim\dinput.dll" (
  set EXTRA=%EXTRA% --add-data "xinput_shim\dinput.dll;xinput_shim"
) else (
  echo NOTE: xinput_shim\dinput.dll not found - build the shim first if you want the Controller section to work.
)
if exist "assets\blank.bik" (
  set EXTRA=%EXTRA% --add-data "assets\blank.bik;assets"
) else (
  echo NOTE: assets\blank.bik not found - the Boot Videos section will use its generated zero-frame clip.
)

REM 5) Build.
REM    --collect-all customtkinter  bundles its Tcl theme JSON (REQUIRED, else the
REM                                 one-file exe crashes at startup).
REM    --add-data ships bundled files; they are read from sys._MEIPASS at runtime.
%PY% -m PyInstaller ^
  --onefile ^
  --windowed ^
  --name StarlancerStudio ^
  --icon "assets\app.ico" ^
  --collect-all customtkinter ^
  --hidden-import darkdetect ^
  --add-data "xinput_shim\xinput_shim.ini;xinput_shim" ^
  --add-data "assets\app.ico;assets" ^
  %EXTRA% ^
  slstudio_app.py

echo.
echo Done. Output: dist\StarlancerStudio.exe
endlocal
