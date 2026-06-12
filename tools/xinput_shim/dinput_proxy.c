/*
 * dinput_proxy.c - Starlancer XInput controller shim (proxy dinput.dll), v1 (no rumble).
 *
 * Starlancer (2000) is DirectInput-only and predates XInput, so a modern Xbox-style
 * pad works only through DInput's legacy path - which collapses LT/RT onto a single
 * shared Z axis and offers no separate triggers. This proxy dinput.dll sits next to
 * lancer.exe (DInput is loaded by name, so a local copy wins) and:
 *
 *   - FORWARDS keyboard + mouse to the real system dinput.dll untouched (the game
 *     creates those by GUID_SysKeyboard / GUID_SysMouse and relies on them - getting
 *     them wrong makes the game unplayable), and
 *   - SYNTHESIZES the joystick from XInput, exposing SEPARATE triggers (lRx = LT,
 *     lRy = RT) plus both sticks, the D-pad as a POV hat, and the face/shoulder/stick
 *     buttons.
 *
 * The game's DInput usage was recovered by static RE (see docs/engine-map.md s7):
 *   root  = IDirectInput7A  (DirectInputCreateEx, ver 0x0700, IID @ 0x4dcfb8)
 *   device= IDirectInputDevice7A (IID @ 0x4dcfa8)
 *   joystick: EnumDevices(type=4, flags 0x101 then retry 1) -> CreateDeviceEx ->
 *             SetDataFormat(c_dfDIJoystick) -> SetCooperativeLevel -> GetCapabilities
 *             (reads dwButtons/dwPOVs) -> EnumObjects (sets per-axis DIPROP_RANGE,
 *             -1000..1000) -> SetProperty(AUTOCENTER); runtime read = Poll() +
 *             GetDeviceState(0x50 = DIJOYSTATE).
 * Reporting NO force feedback routes the game down its no-FF path (the 0x101 enum
 * finds nothing -> it retries with flags=1 and clears its FF flag), so v1 needs no
 * effect objects. Rumble (.frc -> XInput vibration) is deliberately deferred.
 *
 * Build: 32-bit, MSVC - see build.bat. Static project: this DLL is OUR code; it is
 * never loaded into the game by us. In-game verification is the user's.
 */
#define CINTERFACE
#define DIRECTINPUT_VERSION 0x0700
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <dinput.h>
#include <xinput.h>
#include <stdio.h>

/* ------------------------------------------------------------------ options */
typedef struct {
    int  twistRightStickX;   /* right stick X -> lRz (twist). default on  */
    int  rightStickYtoZ;     /* right stick Y -> lZ.          default on  */
    int  dpadAsPOV;          /* D-pad -> POV hat (else buttons). default on */
    int  invertY;            /* invert stick Y.               default off */
    int  separateTriggers;   /* LT->lRx, RT->lRy.             default on  */
    int  deadzone;           /* left/right stick deadzone (XInput units)  */
} ShimCfg;

static ShimCfg g_cfg = { 1, 1, 1, 0, 1, XINPUT_GAMEPAD_LEFT_THUMB_DEADZONE };

/* our synthetic joystick instance/product GUID (private to this shim) */
/* {F1E2D3C4-0001-0007-5354-41524C414E43}  ("STARLANC") */
static const GUID GUID_ShimJoystick =
    { 0xF1E2D3C4, 0x0001, 0x0007, { 0x53,0x54,0x41,0x52,0x4C,0x41,0x4E,0x43 } };

/* ------------------------------------------------------- real dinput.dll ----*/
static HMODULE g_real;
static HRESULT (WINAPI *p_DICreateA)(HINSTANCE, DWORD, LPDIRECTINPUTA*, LPUNKNOWN);
static HRESULT (WINAPI *p_DICreateW)(HINSTANCE, DWORD, LPDIRECTINPUTW*, LPUNKNOWN);
static HRESULT (WINAPI *p_DICreateEx)(HINSTANCE, DWORD, REFIID, LPVOID*, LPUNKNOWN);

static void load_real(void) {
    char path[MAX_PATH];
    UINT n;
    if (g_real) return;
    n = GetSystemDirectoryA(path, MAX_PATH);
    if (n == 0 || n > MAX_PATH - 12) return;
    lstrcatA(path, "\\dinput.dll");
    g_real = LoadLibraryA(path);            /* absolute path: never re-load self */
    if (!g_real) return;
    p_DICreateA  = (void*)GetProcAddress(g_real, "DirectInputCreateA");
    p_DICreateW  = (void*)GetProcAddress(g_real, "DirectInputCreateW");
    p_DICreateEx = (void*)GetProcAddress(g_real, "DirectInputCreateEx");
}

EXTERN_C IMAGE_DOS_HEADER __ImageBase;   /* set by the linker; our own module base */

static void load_cfg(void) {
    char path[MAX_PATH]; char dir[MAX_PATH]; char *p;
    /* xinput_shim.ini lives beside this DLL (next to lancer.exe) */
    if (!GetModuleFileNameA((HMODULE)&__ImageBase, dir, MAX_PATH)) goto done;
    lstrcpynA(path, dir, MAX_PATH);
    p = path; { char *last = path; for (; *p; ++p) if (*p=='\\'||*p=='/') last = p+1; *last = 0; }
    lstrcatA(path, "xinput_shim.ini");
    if (GetFileAttributesA(path) == INVALID_FILE_ATTRIBUTES) goto done;
    g_cfg.twistRightStickX = GetPrivateProfileIntA("mapping", "TwistRightStickX", g_cfg.twistRightStickX, path);
    g_cfg.rightStickYtoZ   = GetPrivateProfileIntA("mapping", "RightStickYToZ",   g_cfg.rightStickYtoZ,   path);
    g_cfg.dpadAsPOV        = GetPrivateProfileIntA("mapping", "DPadAsPOV",        g_cfg.dpadAsPOV,        path);
    g_cfg.invertY          = GetPrivateProfileIntA("mapping", "InvertY",          g_cfg.invertY,          path);
    g_cfg.separateTriggers = GetPrivateProfileIntA("mapping", "SeparateTriggers", g_cfg.separateTriggers, path);
    g_cfg.deadzone         = GetPrivateProfileIntA("mapping", "Deadzone",         g_cfg.deadzone,         path);
done: ;
}

/* ===================================================================== JOY ==*/
typedef struct {
    const IDirectInputDevice7AVtbl *lpVtbl;
    LONG  ref;
    BOOL  acquired;
    LONG  axisMin, axisMax;     /* captured from SetProperty(DIPROP_RANGE) */
} XJoy;

static LONG scale_axis(SHORT v, LONG lo, LONG hi) {
    /* XInput thumb [-32768,32767] -> [lo,hi] with a centred deadzone */
    int dz = g_cfg.deadzone, a = v;
    if (a > -dz && a < dz) a = 0;
    return lo + (LONG)(((double)(a + 32768) / 65535.0) * (hi - lo));
}
static LONG scale_trigger(BYTE t, LONG lo, LONG hi) {
    /* XInput trigger [0,255] -> [lo,hi] */
    return lo + (LONG)(((double)t / 255.0) * (hi - lo));
}

static HRESULT fill_state(XJoy *j, DIJOYSTATE *st) {
    XINPUT_STATE xs; DWORD r; const XINPUT_GAMEPAD *g; WORD b; int i;
    LONG lo = j->axisMin, hi = j->axisMax, mid = (j->axisMin + j->axisMax) / 2;
    ZeroMemory(st, sizeof(*st));
    for (i = 0; i < 4; i++) st->rgdwPOV[i] = (DWORD)-1;   /* POV centred */
    st->lX = st->lY = st->lZ = st->lRx = st->lRy = st->lRz = mid;
    r = XInputGetState(0, &xs);
    if (r != ERROR_SUCCESS) return DI_OK;                /* no pad: neutral */
    g = &xs.Gamepad;
    st->lX = scale_axis(g->sThumbLX, lo, hi);
    st->lY = scale_axis((SHORT)(g->sThumbLY == -32768 ? 32767 : -g->sThumbLY) * (g_cfg.invertY ? -1 : 1), lo, hi);
    if (g_cfg.twistRightStickX) st->lRz = scale_axis(g->sThumbRX, lo, hi);
    if (g_cfg.rightStickYtoZ)   st->lZ  = scale_axis((SHORT)(g->sThumbRY == -32768 ? 32767 : -g->sThumbRY), lo, hi);
    if (g_cfg.separateTriggers) {
        st->lRx = scale_trigger(g->bLeftTrigger,  lo, hi);   /* LT (separate!) */
        st->lRy = scale_trigger(g->bRightTrigger, lo, hi);   /* RT (separate!) */
    }
    b = g->wButtons;
    if (g_cfg.dpadAsPOV) {
        int up = !!(b & XINPUT_GAMEPAD_DPAD_UP),    dn = !!(b & XINPUT_GAMEPAD_DPAD_DOWN);
        int lf = !!(b & XINPUT_GAMEPAD_DPAD_LEFT),  rt = !!(b & XINPUT_GAMEPAD_DPAD_RIGHT);
        DWORD pov = (DWORD)-1;
        if (up && rt) pov = 4500; else if (rt && dn) pov = 13500;
        else if (dn && lf) pov = 22500; else if (lf && up) pov = 31500;
        else if (up) pov = 0; else if (rt) pov = 9000;
        else if (dn) pov = 18000; else if (lf) pov = 27000;
        st->rgdwPOV[0] = pov;
    }
    /* face/shoulder/stick/start/back buttons -> rgbButtons[0..9] */
    st->rgbButtons[0] = (b & XINPUT_GAMEPAD_A) ? 0x80 : 0;
    st->rgbButtons[1] = (b & XINPUT_GAMEPAD_B) ? 0x80 : 0;
    st->rgbButtons[2] = (b & XINPUT_GAMEPAD_X) ? 0x80 : 0;
    st->rgbButtons[3] = (b & XINPUT_GAMEPAD_Y) ? 0x80 : 0;
    st->rgbButtons[4] = (b & XINPUT_GAMEPAD_LEFT_SHOULDER)  ? 0x80 : 0;
    st->rgbButtons[5] = (b & XINPUT_GAMEPAD_RIGHT_SHOULDER) ? 0x80 : 0;
    st->rgbButtons[6] = (b & XINPUT_GAMEPAD_BACK)  ? 0x80 : 0;
    st->rgbButtons[7] = (b & XINPUT_GAMEPAD_START) ? 0x80 : 0;
    st->rgbButtons[8] = (b & XINPUT_GAMEPAD_LEFT_THUMB)  ? 0x80 : 0;
    st->rgbButtons[9] = (b & XINPUT_GAMEPAD_RIGHT_THUMB) ? 0x80 : 0;
    if (!g_cfg.dpadAsPOV) {
        st->rgbButtons[10] = (b & XINPUT_GAMEPAD_DPAD_UP)    ? 0x80 : 0;
        st->rgbButtons[11] = (b & XINPUT_GAMEPAD_DPAD_DOWN)  ? 0x80 : 0;
        st->rgbButtons[12] = (b & XINPUT_GAMEPAD_DPAD_LEFT)  ? 0x80 : 0;
        st->rgbButtons[13] = (b & XINPUT_GAMEPAD_DPAD_RIGHT) ? 0x80 : 0;
    }
    return DI_OK;
}

/* ---- IDirectInputDevice7A methods ---- */
#define JOY(p) ((XJoy*)(p))
static HRESULT STDMETHODCALLTYPE J_QI(IDirectInputDevice7A *t, REFIID riid, void **o) {
    if (IsEqualIID(riid, &IID_IUnknown) || IsEqualIID(riid, &IID_IDirectInputDeviceA) ||
        IsEqualIID(riid, &IID_IDirectInputDevice2A) || IsEqualIID(riid, &IID_IDirectInputDevice7A)) {
        t->lpVtbl->AddRef(t); *o = t; return S_OK;
    }
    *o = NULL; return E_NOINTERFACE;
}
static ULONG STDMETHODCALLTYPE J_AddRef(IDirectInputDevice7A *t) { return InterlockedIncrement(&JOY(t)->ref); }
static ULONG STDMETHODCALLTYPE J_Release(IDirectInputDevice7A *t) {
    LONG r = InterlockedDecrement(&JOY(t)->ref);
    if (r == 0) HeapFree(GetProcessHeap(), 0, t);
    return r;
}
static HRESULT STDMETHODCALLTYPE J_GetCapabilities(IDirectInputDevice7A *t, LPDIDEVCAPS c) {
    if (!c || c->dwSize < 0x18) return DIERR_INVALIDPARAM;   /* need through dwPOVs (+0x14) */
    c->dwFlags   = DIDC_ATTACHED;
    c->dwDevType = MAKEWORD(DIDEVTYPE_JOYSTICK, DIDEVTYPEJOYSTICK_GAMEPAD);
    c->dwAxes    = 6;
    c->dwButtons = g_cfg.dpadAsPOV ? 10 : 14;
    c->dwPOVs    = g_cfg.dpadAsPOV ? 1 : 0;
    return DI_OK;
}
/* enumerate axes (X,Y,Z,Rx,Ry,Rz), the POV, and buttons so the game configures them */
static HRESULT STDMETHODCALLTYPE J_EnumObjects(IDirectInputDevice7A *t, LPDIENUMDEVICEOBJECTSCALLBACKA cb,
                                               LPVOID pv, DWORD flags) {
    DIDEVICEOBJECTINSTANCEA o; int i, nb;
    const GUID *axg[6]   = { &GUID_XAxis,&GUID_YAxis,&GUID_ZAxis,&GUID_RxAxis,&GUID_RyAxis,&GUID_RzAxis };
    const DWORD axofs[6] = { DIJOFS_X,DIJOFS_Y,DIJOFS_Z,DIJOFS_RX,DIJOFS_RY,DIJOFS_RZ };
    if (!cb) return DIERR_INVALIDPARAM;
    if (flags == DIDFT_ALL || (flags & DIDFT_AXIS)) {
        for (i = 0; i < 6; i++) {
            ZeroMemory(&o, sizeof(o)); o.dwSize = sizeof(o);
            o.guidType = *axg[i]; o.dwOfs = axofs[i];
            o.dwType = DIDFT_ABSAXIS | DIDFT_MAKEINSTANCE(i);
            o.dwFlags = DIDOI_ASPECTPOSITION;
            wsprintfA(o.tszName, "Axis %d", i);
            if (cb(&o, pv) == DIENUM_STOP) return DI_OK;
        }
    }
    if ((flags == DIDFT_ALL || (flags & DIDFT_POV)) && g_cfg.dpadAsPOV) {
        ZeroMemory(&o, sizeof(o)); o.dwSize = sizeof(o);
        o.guidType = GUID_POV; o.dwOfs = DIJOFS_POV(0);
        o.dwType = DIDFT_POV | DIDFT_MAKEINSTANCE(0);
        lstrcpyA(o.tszName, "Hat Switch");
        if (cb(&o, pv) == DIENUM_STOP) return DI_OK;
    }
    if (flags == DIDFT_ALL || (flags & DIDFT_BUTTON)) {
        nb = g_cfg.dpadAsPOV ? 10 : 14;
        for (i = 0; i < nb; i++) {
            ZeroMemory(&o, sizeof(o)); o.dwSize = sizeof(o);
            o.guidType = GUID_Button; o.dwOfs = DIJOFS_BUTTON(i);
            o.dwType = DIDFT_PSHBUTTON | DIDFT_MAKEINSTANCE(i);
            wsprintfA(o.tszName, "Button %d", i);
            if (cb(&o, pv) == DIENUM_STOP) return DI_OK;
        }
    }
    return DI_OK;
}
static HRESULT STDMETHODCALLTYPE J_GetProperty(IDirectInputDevice7A *t, REFGUID g, LPDIPROPHEADER h) {
    if (g == DIPROP_RANGE && h && h->dwSize >= sizeof(DIPROPRANGE)) {
        LPDIPROPRANGE r = (LPDIPROPRANGE)h; r->lMin = JOY(t)->axisMin; r->lMax = JOY(t)->axisMax;
    }
    return DI_OK;
}
static HRESULT STDMETHODCALLTYPE J_SetProperty(IDirectInputDevice7A *t, REFGUID g, LPCDIPROPHEADER h) {
    if (g == DIPROP_RANGE && h && h->dwSize >= sizeof(DIPROPRANGE)) {
        LPCDIPROPRANGE r = (LPCDIPROPRANGE)h;        /* honour the range the game sets */
        if (r->lMin < r->lMax) { JOY(t)->axisMin = r->lMin; JOY(t)->axisMax = r->lMax; }
    }
    return DI_OK;   /* accept deadzone/saturation/autocenter/axismode silently */
}
static HRESULT STDMETHODCALLTYPE J_Acquire(IDirectInputDevice7A *t)   { JOY(t)->acquired = TRUE;  return DI_OK; }
static HRESULT STDMETHODCALLTYPE J_Unacquire(IDirectInputDevice7A *t) { JOY(t)->acquired = FALSE; return DI_OK; }
static HRESULT STDMETHODCALLTYPE J_GetDeviceState(IDirectInputDevice7A *t, DWORD cb, LPVOID p) {
    if (!p || cb < sizeof(DIJOYSTATE)) return DIERR_INVALIDPARAM;
    return fill_state(JOY(t), (DIJOYSTATE*)p);   /* acquired-or-not: report neutral/live */
}
static HRESULT STDMETHODCALLTYPE J_GetDeviceData(IDirectInputDevice7A *t, DWORD cb, LPDIDEVICEOBJECTDATA d,
                                                 LPDWORD n, DWORD f) { if (n) *n = 0; return DI_OK; }
static HRESULT STDMETHODCALLTYPE J_SetDataFormat(IDirectInputDevice7A *t, LPCDIDATAFORMAT f) { return DI_OK; }
static HRESULT STDMETHODCALLTYPE J_SetEventNotification(IDirectInputDevice7A *t, HANDLE h) { return DI_OK; }
static HRESULT STDMETHODCALLTYPE J_SetCooperativeLevel(IDirectInputDevice7A *t, HWND w, DWORD f) { return DI_OK; }
static HRESULT STDMETHODCALLTYPE J_GetObjectInfo(IDirectInputDevice7A *t, LPDIDEVICEOBJECTINSTANCEA o,
                                                 DWORD obj, DWORD how) { return DI_OK; }
static HRESULT STDMETHODCALLTYPE J_GetDeviceInfo(IDirectInputDevice7A *t, LPDIDEVICEINSTANCEA i) {
    if (!i) return DIERR_INVALIDPARAM;
    i->guidInstance = GUID_ShimJoystick; i->guidProduct = GUID_ShimJoystick;
    i->dwDevType = MAKEWORD(DIDEVTYPE_JOYSTICK, DIDEVTYPEJOYSTICK_GAMEPAD);
    lstrcpyA(i->tszInstanceName, "XInput Controller");
    lstrcpyA(i->tszProductName,  "XInput Controller");
    return DI_OK;
}
static HRESULT STDMETHODCALLTYPE J_RunControlPanel(IDirectInputDevice7A *t, HWND w, DWORD f) { return DI_OK; }
static HRESULT STDMETHODCALLTYPE J_Initialize(IDirectInputDevice7A *t, HINSTANCE h, DWORD v, REFGUID g) { return DI_OK; }
static HRESULT STDMETHODCALLTYPE J_Poll(IDirectInputDevice7A *t) { XINPUT_STATE s; XInputGetState(0,&s); return DI_OK; }
/* Force feedback + effect-file methods: unsupported. The game uses the no-FF path
   (our pad reports no FF), so these are never called - but they MUST still pop the
   right number of __stdcall args if they ever were, so each has correct arity. */
static HRESULT STDMETHODCALLTYPE J_u2(void *t, void *a) { return DIERR_UNSUPPORTED; }
static HRESULT STDMETHODCALLTYPE J_u3(void *t, void *a, void *b) { return DIERR_UNSUPPORTED; }
static HRESULT STDMETHODCALLTYPE J_u4(void *t, void *a, void *b, void *c) { return DIERR_UNSUPPORTED; }
static HRESULT STDMETHODCALLTYPE J_u5(void *t, void *a, void *b, void *c, void *d) { return DIERR_UNSUPPORTED; }

/* exact IDirectInputDevice7A vtable order (IUnknown + DeviceA + Device2A + Device7A).
   Poll lands at index 25 == offset 0x64, matching the game's call site. */
static const IDirectInputDevice7AVtbl g_joyVtbl = {
    J_QI, J_AddRef, J_Release,                                   /* 0-2  IUnknown */
    J_GetCapabilities, J_EnumObjects, J_GetProperty, J_SetProperty,   /* 3-6 */
    J_Acquire, J_Unacquire, J_GetDeviceState, J_GetDeviceData,        /* 7-10 */
    J_SetDataFormat, J_SetEventNotification, J_SetCooperativeLevel,   /* 11-13 */
    J_GetObjectInfo, J_GetDeviceInfo, J_RunControlPanel, J_Initialize,/* 14-17 */
    (void*)J_u5 /*CreateEffect       18*/, (void*)J_u4 /*EnumEffects        19*/,
    (void*)J_u3 /*GetEffectInfo      20*/, (void*)J_u2 /*GetForceFeedbackState 21*/,
    (void*)J_u2 /*SendFFCommand      22*/, (void*)J_u4 /*EnumCreatedEffects  23*/,
    (void*)J_u2 /*Escape             24*/, J_Poll /*                        25 (0x64)*/,
    (void*)J_u5 /*SendDeviceData     26*/, (void*)J_u5 /*EnumEffectsInFile   27*/,
    (void*)J_u5 /*WriteEffectToFile  28*/
};

static IDirectInputDevice7A *make_joy(void) {
    XJoy *j = HeapAlloc(GetProcessHeap(), HEAP_ZERO_MEMORY, sizeof(XJoy));
    if (!j) return NULL;
    j->lpVtbl = &g_joyVtbl; j->ref = 1;
    j->axisMin = -1000; j->axisMax = 1000;   /* matches the game's EnumObjects ranges */
    return (IDirectInputDevice7A*)j;
}

/* ==================================================================== ROOT ==*/
typedef struct {
    const IDirectInput7AVtbl *lpVtbl;
    LONG  ref;
    IDirectInput7A *real;
} ProxyDI;
#define DI(p) ((ProxyDI*)(p))

static HRESULT STDMETHODCALLTYPE R_QI(IDirectInput7A *t, REFIID riid, void **o) {
    if (IsEqualIID(riid, &IID_IUnknown) || IsEqualIID(riid, &IID_IDirectInputA) ||
        IsEqualIID(riid, &IID_IDirectInput2A) || IsEqualIID(riid, &IID_IDirectInput7A)) {
        t->lpVtbl->AddRef(t); *o = t; return S_OK;
    }
    *o = NULL; return E_NOINTERFACE;
}
static ULONG STDMETHODCALLTYPE R_AddRef(IDirectInput7A *t) { return InterlockedIncrement(&DI(t)->ref); }
static ULONG STDMETHODCALLTYPE R_Release(IDirectInput7A *t) {
    LONG r = InterlockedDecrement(&DI(t)->ref);
    if (r == 0) {
        if (DI(t)->real) DI(t)->real->lpVtbl->Release(DI(t)->real);
        HeapFree(GetProcessHeap(), 0, t);
    }
    return r;
}
static HRESULT STDMETHODCALLTYPE R_CreateDeviceEx(IDirectInput7A *t, REFGUID rg, REFIID riid, void **o, LPUNKNOWN u) {
    if (rg && IsEqualGUID(rg, &GUID_ShimJoystick)) {   /* our synthetic pad */
        IDirectInputDevice7A *j = make_joy();
        if (!j) return E_OUTOFMEMORY;
        *o = j; return DI_OK;
    }
    /* keyboard / mouse / anything real -> forward to the real dinput verbatim */
    if (DI(t)->real) return DI(t)->real->lpVtbl->CreateDeviceEx(DI(t)->real, rg, riid, o, u);
    *o = NULL; return DIERR_DEVICENOTREG;
}
static HRESULT STDMETHODCALLTYPE R_CreateDevice(IDirectInput7A *t, REFGUID rg, LPDIRECTINPUTDEVICEA *o, LPUNKNOWN u) {
    if (rg && IsEqualGUID(rg, &GUID_ShimJoystick)) {
        IDirectInputDevice7A *j = make_joy();
        if (!j) return E_OUTOFMEMORY;
        *o = (LPDIRECTINPUTDEVICEA)j; return DI_OK;
    }
    if (DI(t)->real) return DI(t)->real->lpVtbl->CreateDevice(DI(t)->real, rg, o, u);
    *o = NULL; return DIERR_DEVICENOTREG;
}
static HRESULT STDMETHODCALLTYPE R_EnumDevices(IDirectInput7A *t, DWORD devType,
                                               LPDIENUMDEVICESCALLBACKA cb, LPVOID pv, DWORD flags) {
    BYTE base = (BYTE)(devType & 0xff);
    /* present our synthetic XInput pad for joystick enums, unless a FF device was
       demanded (DIEDFL_FORCEFEEDBACK) - omitting it there steers the game onto its
       clean no-FF path. For non-joystick enums, defer to the real dinput. */
    if (cb && (devType == 0 || base == DIDEVTYPE_JOYSTICK) && !(flags & DIEDFL_FORCEFEEDBACK)) {
        DIDEVICEINSTANCEA di; ZeroMemory(&di, sizeof(di)); di.dwSize = sizeof(di);
        di.guidInstance = GUID_ShimJoystick; di.guidProduct = GUID_ShimJoystick;
        di.dwDevType = MAKEWORD(DIDEVTYPE_JOYSTICK, DIDEVTYPEJOYSTICK_GAMEPAD);
        lstrcpyA(di.tszInstanceName, "XInput Controller");
        lstrcpyA(di.tszProductName,  "XInput Controller");
        cb(&di, pv);          /* one synthetic pad; ignore STOP (only one anyway) */
        return DI_OK;
    }
    if (DI(t)->real) return DI(t)->real->lpVtbl->EnumDevices(DI(t)->real, devType, cb, pv, flags);
    return DI_OK;
}
static HRESULT STDMETHODCALLTYPE R_GetDeviceStatus(IDirectInput7A *t, REFGUID rg) {
    if (rg && IsEqualGUID(rg, &GUID_ShimJoystick)) return DI_OK;
    if (DI(t)->real) return DI(t)->real->lpVtbl->GetDeviceStatus(DI(t)->real, rg);
    return DI_OK;
}
static HRESULT STDMETHODCALLTYPE R_RunControlPanel(IDirectInput7A *t, HWND w, DWORD f) {
    if (DI(t)->real) return DI(t)->real->lpVtbl->RunControlPanel(DI(t)->real, w, f);
    return DI_OK;
}
static HRESULT STDMETHODCALLTYPE R_Initialize(IDirectInput7A *t, HINSTANCE h, DWORD v) {
    if (DI(t)->real) return DI(t)->real->lpVtbl->Initialize(DI(t)->real, h, v);
    return DI_OK;
}
static HRESULT STDMETHODCALLTYPE R_FindDevice(IDirectInput7A *t, REFGUID rg, LPCSTR n, LPGUID o) {
    if (DI(t)->real) return DI(t)->real->lpVtbl->FindDevice(DI(t)->real, rg, n, o);
    return DIERR_DEVICENOTREG;
}
static const IDirectInput7AVtbl g_rootVtbl = {
    R_QI, R_AddRef, R_Release, R_CreateDevice, R_EnumDevices, R_GetDeviceStatus,
    R_RunControlPanel, R_Initialize, R_FindDevice, R_CreateDeviceEx
};

static HRESULT wrap_root(IDirectInput7A *real, void **out) {
    ProxyDI *p = HeapAlloc(GetProcessHeap(), HEAP_ZERO_MEMORY, sizeof(ProxyDI));
    if (!p) { if (real) real->lpVtbl->Release(real); return E_OUTOFMEMORY; }
    p->lpVtbl = &g_rootVtbl; p->ref = 1; p->real = real;
    *out = p; return DI_OK;
}

/* ================================================================= EXPORTS ==*/
HRESULT WINAPI DirectInputCreateEx(HINSTANCE h, DWORD ver, REFIID riid, LPVOID *out, LPUNKNOWN unk) {
    IDirectInput7A *real = NULL; HRESULT hr;
    if (!out) return E_POINTER;
    load_real();
    if (!p_DICreateEx) return DIERR_OLDDIRECTINPUTVERSION;
    /* always obtain a real IDirectInput7A for keyboard/mouse forwarding */
    hr = p_DICreateEx(h, ver, &IID_IDirectInput7A, (void**)&real, unk);
    if (FAILED(hr)) real = NULL;     /* still proxy; joystick works, kbd/mouse would not */
    return wrap_root(real, out);
}
HRESULT WINAPI DirectInputCreateA(HINSTANCE h, DWORD ver, LPDIRECTINPUTA *out, LPUNKNOWN unk) {
    return DirectInputCreateEx(h, ver, &IID_IDirectInput7A, (void**)out, unk);
}
HRESULT WINAPI DirectInputCreateW(HINSTANCE h, DWORD ver, LPDIRECTINPUTW *out, LPUNKNOWN unk) {
    /* Starlancer uses the ANSI path; provide W defensively by delegating to the real one. */
    load_real();
    if (p_DICreateW) return p_DICreateW(h, ver, out, unk);
    return DIERR_OLDDIRECTINPUTVERSION;
}

BOOL WINAPI DllMain(HINSTANCE inst, DWORD reason, LPVOID resv) {
    if (reason == DLL_PROCESS_ATTACH) {
        DisableThreadLibraryCalls(inst);
        load_cfg();
    }
    return TRUE;
}
