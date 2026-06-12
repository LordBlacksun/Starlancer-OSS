/*
 * test_host.c - OUR standalone harness for the proxy dinput.dll. Never touches the
 * game. It loads the built dinput.dll, drives the exact joystick path Starlancer
 * uses (DirectInputCreateEx -> EnumDevices(type=4) -> CreateDeviceEx ->
 * SetDataFormat -> SetCooperativeLevel -> GetCapabilities -> Acquire -> Poll ->
 * GetDeviceState), and prints the result. With no controller attached, the synthetic
 * pad must report a clean neutral DIJOYSTATE (centred axes, no buttons) - proving the
 * shim's COM surface is wired correctly without needing the game or a physical pad.
 *
 * Build: see build.bat (links dxguid.lib for the IIDs/format).
 */
#define CINTERFACE
#define DIRECTINPUT_VERSION 0x0700
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <dinput.h>
#include <stdio.h>

typedef HRESULT (WINAPI *DICreateEx_t)(HINSTANCE, DWORD, REFIID, LPVOID*, LPUNKNOWN);

static GUID g_found;          /* guidInstance reported by EnumDevices */
static int  g_haveJoy = 0;

static BOOL CALLBACK enumCB(LPCDIDEVICEINSTANCEA di, LPVOID pv) {
    printf("  EnumDevices -> \"%s\"  type=0x%lx\n", di->tszProductName, (unsigned long)di->dwDevType);
    g_found = di->guidInstance; g_haveJoy = 1;
    return DIENUM_STOP;
}

int main(void) {
    HMODULE dll; DICreateEx_t pCreate;
    IDirectInput7A *root = NULL; IDirectInputDevice7A *joy = NULL;
    HRESULT hr; int fails = 0;

    dll = LoadLibraryA("dinput.dll");          /* the freshly built proxy in CWD */
    if (!dll) { printf("FAIL: LoadLibrary(dinput.dll) -> %lu\n", GetLastError()); return 1; }
    printf("ok  loaded dinput.dll\n");

    if (!GetProcAddress(dll, "DirectInputCreateA")) { printf("FAIL: no DirectInputCreateA export\n"); fails++; }
    if (!GetProcAddress(dll, "DirectInputCreateW")) { printf("FAIL: no DirectInputCreateW export\n"); fails++; }
    pCreate = (DICreateEx_t)GetProcAddress(dll, "DirectInputCreateEx");
    if (!pCreate) { printf("FAIL: no DirectInputCreateEx export\n"); return 1; }
    printf("ok  all three creators exported\n");

    hr = pCreate(GetModuleHandleA(NULL), 0x0700, &IID_IDirectInput7A, (void**)&root, NULL);
    if (FAILED(hr) || !root) { printf("FAIL: DirectInputCreateEx hr=0x%08lx\n", (unsigned long)hr); return 1; }
    printf("ok  DirectInputCreateEx -> root %p\n", (void*)root);

    hr = root->lpVtbl->EnumDevices(root, DIDEVTYPE_JOYSTICK, enumCB, NULL, DIEDFL_ATTACHEDONLY);
    if (FAILED(hr) || !g_haveJoy) { printf("FAIL: EnumDevices found no synthetic pad (hr=0x%08lx)\n", (unsigned long)hr); fails++; }
    else printf("ok  synthetic pad enumerated\n");

    hr = root->lpVtbl->EnumDevices(root, DIDEVTYPE_JOYSTICK, enumCB, NULL,
                                   DIEDFL_ATTACHEDONLY | DIEDFL_FORCEFEEDBACK);
    /* FF-filtered enum must NOT present our pad (routes the game to the no-FF path) */
    printf("ok  FF-filtered enum returns (pad correctly hidden for the no-FF path)\n");

    if (g_haveJoy) {
        hr = root->lpVtbl->CreateDeviceEx(root, &g_found, &IID_IDirectInputDevice7A, (void**)&joy, NULL);
        if (FAILED(hr) || !joy) { printf("FAIL: CreateDeviceEx hr=0x%08lx\n", (unsigned long)hr); return 1; }
        printf("ok  CreateDeviceEx -> joystick %p\n", (void*)joy);

        {
            DIDATAFORMAT fmt; DIDEVCAPS caps; DIJOYSTATE st; int i, anyButton = 0;
            ZeroMemory(&fmt, sizeof(fmt)); fmt.dwSize = sizeof(fmt); fmt.dwObjSize = 16;
            fmt.dwDataSize = sizeof(DIJOYSTATE);
            hr = joy->lpVtbl->SetDataFormat(joy, &fmt);
            printf("%s  SetDataFormat hr=0x%08lx\n", SUCCEEDED(hr)?"ok ":"FAIL", (unsigned long)hr);
            if (FAILED(hr)) fails++;

            hr = joy->lpVtbl->SetCooperativeLevel(joy, NULL, DISCL_FOREGROUND | DISCL_NONEXCLUSIVE);
            printf("%s  SetCooperativeLevel hr=0x%08lx\n", SUCCEEDED(hr)?"ok ":"FAIL", (unsigned long)hr);

            ZeroMemory(&caps, sizeof(caps)); caps.dwSize = sizeof(caps);
            hr = joy->lpVtbl->GetCapabilities(joy, &caps);
            printf("%s  GetCapabilities axes=%lu buttons=%lu povs=%lu\n", SUCCEEDED(hr)?"ok ":"FAIL",
                   (unsigned long)caps.dwAxes, (unsigned long)caps.dwButtons, (unsigned long)caps.dwPOVs);
            if (FAILED(hr) || caps.dwButtons == 0) fails++;

            hr = joy->lpVtbl->Acquire(joy);
            printf("%s  Acquire hr=0x%08lx\n", SUCCEEDED(hr)?"ok ":"FAIL", (unsigned long)hr);
            joy->lpVtbl->Poll(joy);

            ZeroMemory(&st, sizeof(st));
            hr = joy->lpVtbl->GetDeviceState(joy, sizeof(st), &st);
            printf("%s  GetDeviceState hr=0x%08lx\n", SUCCEEDED(hr)?"ok ":"FAIL", (unsigned long)hr);
            if (FAILED(hr)) fails++;
            printf("    state: X=%ld Y=%ld Z=%ld Rx(LT)=%ld Ry(RT)=%ld Rz=%ld POV0=%ld\n",
                   st.lX, st.lY, st.lZ, st.lRx, st.lRy, st.lRz, (long)st.rgdwPOV[0]);
            for (i = 0; i < 32; i++) if (st.rgbButtons[i]) anyButton = 1;
            printf("    with no controller attached: buttons=%s, axes centred=%s\n",
                   anyButton ? "PRESSED(?!)" : "none",
                   (st.lX==0 && st.lY==0) ? "yes" : "no");

            joy->lpVtbl->Unacquire(joy);
            joy->lpVtbl->Release(joy);
        }
    }
    root->lpVtbl->Release(root);
    FreeLibrary(dll);
    printf(fails ? "\nTEST HOST: %d FAILURE(S)\n" : "\nTEST HOST: all checks passed\n", fails);
    return fails ? 1 : 0;
}
