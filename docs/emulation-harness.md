# Function-level emulation — measuring the engine without running the game

> **Tool:** `tools/sl_emu.py` · **Optional dependency:** `unicorn>=2.0` ·
> **Status:** working; the widescreen fix is now verified by measurement, not only by disassembly.
>
> **The game is never launched.** This harness maps a local copy of the executable into a
> sandboxed CPU emulator as plain memory and interprets the instructions of **one function**.
> There is no Windows loader, no process, no window, no device, no audio, and no imports are
> resolved. It is the same posture the project already took with `sd_emulate.py`, which emulates
> the SafeDisc loader rather than running it, pointed at the engine's own routines instead.

---

## 1. Why this exists

Static analysis tells you what code *says*. Until now every claim in this project rested on
reading disassembly and reasoning about it. That is sound, and it is also unfalsifiable in
practice: a subtly wrong reading of an x87 sequence produces a confident, wrong document, and
nothing in the toolchain can contradict it.

Emulating a single function closes that gap without crossing the project's hard line. The
executable is treated as data throughout. What changes is that the arithmetic is now performed by
the original instructions rather than restated by hand, so a claim about what the code computes
can be checked against what it actually computes.

Three things this buys:

- **A patch can be measured.** The widescreen fix claims it equalises the horizontal and vertical
  projection scales, and that it is a no-op at 4:3. Both halves are now demonstrated numerically,
  against a stock image and a patched one, at several resolutions.
- **Constants stop being assumptions.** `_DAT_004dc420` was carried in the notes as an unnamed
  offset "K". Running the function pins it at **0.1**, because the code reads it out of the image
  itself.
- **Side effects are discovered, not inferred.** Every store the function executes is logged with
  its address and value, so which globals a routine touches is observed rather than taken from a
  decompiler's guess at variable identity.

---

## 2. How it works

```
python tools/sl_emu.py projection <exe> --res 1920x1080 3440x1440
python tools/sl_emu.py compare <stock.exe> <patched.exe>
python tools/sl_emu.py call <exe> 0x4c3a60 --arg-f32 0 0 1 1 0.6 0.8
python tools/sl_emu.py selftest
```

1. **Map.** The PE headers and every section's raw bytes are written at their virtual addresses
   inside one allocation at the image base, sized by `SizeOfImage`. A section whose virtual size
   exceeds its raw size keeps the zero fill the mapping already provides, exactly as the real
   loader would leave it.
2. **Frame.** Arguments are pushed right-to-left as 32-bit words under a return address that
   points at a page of its own, so an ordinary `ret` ends the run.
3. **Fence.** Execution is confined to a list of allowed address regions. Stepping outside all of
   them halts the run. This is what makes stubbing unnecessary: a routine that later calls other
   engine code has already computed everything of interest before its first call.
4. **Record.** A write hook logs every store. A code hook counts instructions and can trace them.

The fence takes a *list* rather than one range for a specific reason. A patched build's hook is a
jump into slack elsewhere in `.text`, so the cave is part of the function under test while being
nowhere near it. `sl_emu` reads the cave addresses out of the sidecar manifest `sl_patch` writes,
which is what lets the same measurement run against both images and mean the same thing.

**A run that stores nothing is reported as unmeasured, never as a pass.** The scale globals are
poisoned with NaN before each run. This mattered immediately: the first comparison against a
patched build halted at the jump into the cave, wrote nothing, and two zeros compared equal, which
looked like a clean result and was not one.

---

## 3. What was measured

### 3.1 The function

`FUN_004C3A60` at `0x4c3a60`, the projection scale and centre writer. It reads the device
dimensions as integers and writes twelve floats:

| Address | Meaning |
|---|---|
| `0x5e81b6` | device width, read with `fild` (integer dword) |
| `0x5e81ba` | device height, read with `fild` (integer dword) |
| `0x5e81be` | horizontal scale, `(width − K) × param_5` |
| `0x5e81d6` | vertical scale, `(height − K) × param_6` |

The engine's own call site passes `param_5 = 0.6` and `param_6 = 0.8`, the `0x3f19999a` and
`0x3f4ccccd` seen in the decompilation. What matters is their ratio: `0.6 / 0.8 = 0.75 = 480/640`,
the 4:3 aspect baked into the projection as a pair of constants.

### 3.2 Stock behaviour

Executed out of the decrypted image, seeding only the device dimensions:

| Resolution | scale_x | scale_y | x/y |
|---|---:|---:|---:|
| 640 × 480 | 383.94000 | 383.92001 | 1.00005 |
| 1024 × 768 | 614.34003 | 614.32001 | 1.00003 |
| 1920 × 1080 | 1151.94006 | 863.91998 | **1.33339** |
| 2560 × 1080 | 1535.94006 | 863.91998 | **1.77787** |
| 3440 × 1440 | 2063.94019 | 1151.92004 | **1.79174** |

Solving from these numbers gives **K = 0.1** and a closed form for the stock ratio:

```
scale_x / scale_y  =  0.75 × (w − 0.1) / (h − 0.1)  ≈  0.75 × (w / h)
```

So the stock projection is square **only** when the display is 4:3, and is stretched horizontally
by exactly the aspect error everywhere else: 33% at 16:9, 78% at 2560×1080. This is the defect the
widescreen fix exists to remove, now stated as a measurement rather than a reading.

### 3.3 Patched behaviour

The same function, executed out of a copy patched with `sl_patch --widescreen`:

| Resolution | stock x/y | patched x/y | verdict |
|---|---:|---:|---|
| 640 × 480 | 1.00005 | 1.00005 | identical, the fix is a no-op |
| 1024 × 768 | 1.00003 | 1.00003 | identical, the fix is a no-op |
| 1920 × 1080 | 1.33339 | **1.00004** | square |
| 2560 × 1080 | 1.77787 | **1.00005** | square |
| 3440 × 1440 | 1.79174 | **1.00004** | square |

At 4:3 the patched image produces bit-identical output to the stock one, which is the no-op claim
demonstrated rather than argued. At every widescreen resolution the two scales agree.

### 3.4 A new finding: the fix is resolution-independent

`sl_patch --widescreen WxH` takes a resolution, so the natural assumption is that a build patched
for 1920×1080 is correct at 1920×1080 and wrong elsewhere. It is not. Two copies of the same stock
image, patched for different resolutions, produce **identical scales to the last digit** at every
test resolution:

| Test resolution | patched for 1920×1080 | patched for 3440×1440 |
|---|---:|---:|
| 1920 × 1080 | 863.95502 / 863.91998 | 863.95502 / 863.91998 |
| 2560 × 1080 | 863.96625 / 863.91998 | 863.96625 / 863.91998 |
| 3440 × 1440 | 1151.96655 / 1151.92004 | 1151.96655 / 1151.92004 |

The reason is visible in the cave the patcher emits, which computes from the **live device
globals** rather than from a baked constant:

```
fild  dword [0x5e81ba]   ; height
fmul  dword [esp+0x1c]   ; × param_6 (0.8)
fidiv dword [0x5e81b6]   ; ÷ width
fstp  dword [esp+0x18]   ; → param_5
fild  dword [0x5e81b6]   ; the displaced original instruction
jmp   back
```

So the resolution argument only affects the *second* cave, which bakes the chosen mode into the
flight globals. The projection maths is correct at whatever resolution the device happens to be.
Practically: the aspect correction does not need re-patching when a user changes resolution, though
re-patching is still what changes which mode the flight code asks for.

### 3.5 The residual, and why it is not an error

The patched scales differ by a small amount rather than being exactly equal:

```
scale_x − scale_y  =  0.08 × (1 − h/w)
```

which is 0.035 at 1920×1080 against a magnitude of 864, four parts in 100,000. It falls out of the
constant K = 0.1 being subtracted before scaling on both axes, and it is far below one pixel. The
stock build shows the same class of residual at 4:3, differing by 0.02 in 384. Squareness is
therefore tested **relatively**, at 0.1%: an absolute tolerance calls the correct case broken,
which it did on the first run here.

---

## 4. Limits

Honest boundaries of the method as it stands:

- **One function at a time.** Nothing resolves imports, so a routine that calls into `srddraw`,
  Miles or Bink cannot be run past that call. For routines like this one the interesting work
  happens first, which is why the fence exists.
- **No operating system.** No heap, no thread-local storage, no registry, no file handles. A
  routine that touches any of those needs those regions seeded by hand.
- **Seeded state is a claim.** The harness sets the device globals before the call. That they are
  the ones the engine sets, at the point it sets them, comes from static analysis and is not itself
  proved here.
- **It cannot tell you how it looks.** The projection is square by measurement. Whether the result
  is *pleasant* at 21:9, whether widgets sit correctly, and whether `srddraw.dll` accepts a back
  buffer that wide are in-game questions, and in-game testing stays with the player.

---

## 5. Worthwhile next targets

- **Differential-test the format parsers.** Run the engine's own `.SHP` and stat-table readers
  against `shp_parse.py` and `slstats.py` on the same bytes. Where they disagree, the spec is
  wrong. This is the strongest available way to close the 25 open questions in the `.SHP` format
  document, and it needs no game data in the repo because the comparison runs on the player's copy.
- **The medal-case fix.** Execute the three patched `_BinkOpen` call sites and confirm the handle
  reaches `DAT_0051d7e8`, rather than reading it from the disassembly.
- **The FOV table.** `sl_patch --fov-table` prints computed angles; the emulator can derive them
  from the executed projection instead.

---

## Related

- `docs/modern-fixes.md` §3 — the widescreen fix as designed and statically verified
- `docs/engine-map.md` §3 — the projection path and the `srddraw.dll` boundary
- `tools/sl_patch.py` — the patch pack whose manifest this harness reads
