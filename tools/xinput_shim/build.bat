@echo off
REM ---------------------------------------------------------------------------
REM Build the 32-bit Starlancer XInput shim (proxy dinput.dll) + its test host.
REM
REM Starlancer is a 32-bit game, so this MUST be built x86. MSVC is off PATH by
REM design, so this script locates and calls vcvars32.bat itself - you can run it
REM from any plain cmd.exe. (You do NOT need a Developer Command Prompt.)
REM ---------------------------------------------------------------------------
setlocal
cd /d "%~dp0"
REM Adjust VCV if your Visual Studio lives elsewhere / is a different edition.
set "VCV=C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars32.bat"
if not exist "%VCV%" set "VCV=C:\Program Files (x86)\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars32.bat"
if not exist "%VCV%" (
  echo [build] Could not find vcvars32.bat. Edit VCV in build.bat to point at your
  echo         Visual Studio's VC\Auxiliary\Build\vcvars32.bat, then re-run.
  exit /b 1
)
call "%VCV%" >nul || (echo [build] vcvars32 failed & exit /b 1)

echo [build] compiling dinput.dll (x86)...
cl /nologo /LD /O2 /W3 /DNDEBUG dinput_proxy.c ^
   /Fe:dinput.dll ^
   /link /DEF:xinput_shim.def dxguid.lib xinput.lib user32.lib kernel32.lib advapi32.lib
if errorlevel 1 (echo [build] DLL build FAILED & exit /b 1)

echo [build] compiling test_host.exe (x86)...
cl /nologo /O2 /W3 test_host.c /Fe:test_host.exe /link dxguid.lib
if errorlevel 1 (echo [build] test host build FAILED & exit /b 1)

echo [build] OK: dinput.dll + test_host.exe
echo [build] verify exports with:  python ..\pe_inspect.py dinput.dll
echo [build] smoke-test with:      test_host.exe
endlocal
