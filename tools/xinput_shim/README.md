# Starlancer XInput controller shim (proxy `dinput.dll`) — v1, no rumble

Starlancer (2000) is **DirectInput-only** and predates **XInput**, so a modern
Xbox-style pad only works through DInput's legacy path — which **merges the two
triggers onto one shared Z axis** and gives no separate LT/RT. This is a tiny proxy
`dinput.dll` that fixes that natively: it forwards keyboard + mouse to the real
DirectInput untouched, and **synthesizes the joystick from XInput** with **separate
triggers**, both sticks, the D-pad as a POV hat, and all the buttons.

It is a clean drop-in: no exe patch, no installer. Because Windows resolves a
DLL next to the executable before the system copy (and `dinput.dll` is not a
"known DLL"), a local copy wins.

## Install
1. Build `dinput.dll` (see **Build**), or use a release build.
2. Copy **`dinput.dll`** (and optionally **`xinput_shim.ini`**) into your Starlancer
   folder, **next to `lancer.exe`**.
3. In the game's controller setup, calibrate/bind as usual — the pad shows up as
   **"XInput Controller"** with separate triggers.

## Uninstall
Delete `dinput.dll` (and `xinput_shim.ini`) from the game folder. Nothing else is
touched.

## Mapping (default)
| Game axis / input | Source |
|---|---|
| `lX`, `lY` | left stick |
| `lRz` (twist) | right stick X *(TwistRightStickX)* |
| `lZ` | right stick Y *(RightStickYToZ)* |
| `lRx` = **LT**, `lRy` = **RT** | the **separate** triggers *(SeparateTriggers)* |
| POV hat | D-pad *(DPadAsPOV; else buttons 10–13)* |
| Buttons 0–9 | A, B, X, Y, LB, RB, Back, Start, L3, R3 |

All of these are configurable in `xinput_shim.ini` (see that file for keys).

## Build
32-bit (the game is 32-bit). MSVC is off PATH by design; `build.bat` finds and calls
`vcvars32.bat` itself, so run it from any `cmd.exe`:

```
cd tools\xinput_shim
build.bat
```

Outputs `dinput.dll` + `test_host.exe`. Verify and smoke-test (neither runs the game):

```
python ..\pe_inspect.py dinput.dll      # confirms 32-bit + the 3 exports
test_host.exe                           # drives the joystick COM path with no pad
```

`test_host.exe` is **our** harness — it loads the proxy and exercises the exact COM
sequence Starlancer uses (`DirectInputCreateEx` → `EnumDevices` → `CreateDeviceEx` →
`SetDataFormat` → `GetCapabilities` → `Acquire` → `Poll` → `GetDeviceState`). With no
controller attached it must report a clean neutral state.

## Scope / status (v1)
- **No rumble.** The pad reports no force feedback, which routes the game onto its
  clean no-FF path (so the shim needs no effect objects). Translating the game's
  per-weapon `.frc` effects to XInput vibration is deferred to a later version.
- Presents exactly **one** synthetic XInput pad (player 1). Real DInput joysticks are
  not enumerated while the shim is installed.
- **In-game verification is yours.** This project never launches the game; the shim is
  built and structurally tested only (see `test_host.exe`).

## How it works (for the curious)
The game's DInput surface was recovered by static RE (`docs/engine-map.md` §7): root
`IDirectInput7A` (`DirectInputCreateEx`, version `0x0700`), devices
`IDirectInputDevice7A`. Keyboard (`GUID_SysKeyboard`) and mouse (`GUID_SysMouse`) are
created by GUID and **forwarded to the real `dinput.dll`**. The joystick is found via
`EnumDevices(type=4)`; the shim presents one synthetic pad whose `GetDeviceState`
returns a standard 80-byte `DIJOYSTATE` filled from `XInputGetState`. Reporting no FF
makes the game's force-feedback path stand down cleanly.
