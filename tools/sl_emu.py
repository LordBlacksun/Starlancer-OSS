#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 LordBlacksun
# SPDX-License-Identifier: GPL-3.0-only
"""sl_emu.py - run ONE function out of the Starlancer image, in a CPU emulator.

Static analysis tells you what the code says. This tells you what it *computes*,
without the game ever being a process. The PE is mapped into a Unicorn x86-32
machine as plain memory, a synthetic stack is built, one function is entered at
its own address, and execution is stopped the moment control leaves it. There is
no Windows loader, no window, no device, no audio, no imports resolved, and no
game: the emulator interprets instructions and records the memory they touch.

The project already treats emulation as static work (`sd_emulate.py` emulates the
SafeDisc loader rather than running it); this is the same idea aimed at the
engine's own routines.

Why bother, when the disassembly is right there:

  * A patch can be *measured*. The widescreen fix claims it makes the horizontal
    and vertical projection scales equal, and that it changes nothing at 4:3.
    `projection` below runs the real function out of both a stock and a patched
    image and prints the numbers each one produces.
  * Constants stop being assumptions. `_DAT_004dc420` and `_DAT_004dc408` are
    read out of the image by the code itself, at the width the caller asked for.
  * Every store is logged, so a function's side effects are discovered rather
    than inferred from a decompiler's guess at which global is which.

REQUIRES: unicorn  (`pip install unicorn`) - optional, listed in
requirements-optional.txt. Everything else in this repo stays standard library.

SAFETY: this reads a local copy of an executable as data and interprets some of
its instructions in a sandboxed emulator. It does not launch Starlancer, spawn a
process, create a window, or produce sound. It never writes to the input file.

Usage:
    python sl_emu.py projection <exe> [--res 1920x1080] [--verbose]
    python sl_emu.py compare <stock.exe> <patched.exe> [--res 1920x1080 ...]
    python sl_emu.py call <exe> <va> [--arg-f32 1.0 ...] [--u32 VA=VALUE ...]
    python sl_emu.py selftest
"""

import argparse
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import sl_patch                          # noqa: E402  PE parsing + the fix registry

try:
    import unicorn
    from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, UcError
    from unicorn.x86_const import UC_X86_REG_ESP, UC_X86_REG_EIP
    HAVE_UNICORN = True
except ImportError:                       # keep the module importable without it
    unicorn = None
    HAVE_UNICORN = False


# --------------------------------------------------------------- memory layout
STACK_BASE = 0x00200000
STACK_SIZE = 0x00100000
MAGIC_RET = 0x00190000            # a page of its own: EIP landing here == returned
PAGE = 0x1000


def _align_down(x):
    return x & ~(PAGE - 1)


def _align_up(x):
    return (x + PAGE - 1) & ~(PAGE - 1)


# =============================================== the projection function's map ==
# FUN_004c3a60, the projection scale/centre writer. Addresses come from the
# project's Ghidra pass; the emulator confirms them rather than trusting them.
PROJ_FUNC = 0x004C3A60
PROJ_END = 0x004C3C50             # the next function; leaving this range == done
G_DEV_WIDTH = 0x005E81B6          # device width  (integer dword, read with fild)
G_DEV_HEIGHT = 0x005E81BA         # device height (integer dword)
G_SCALE_X = 0x005E81BE            # (width  - K) * param_5
G_SCALE_Y = 0x005E81D6            # (height - K) * param_6
# The engine's own call site passes these: 0x3f19999a and 0x3f4ccccd.
PROJ_ARGS = (0.0, 0.0, 1.0, 1.0, 0.6, 0.8)

# "Square" is a RELATIVE test. The engine offsets both axes by a constant K=0.1
# before scaling, so scale_x and scale_y never land on bit-identical values even
# when the aspect is exactly right: at 4:3 the stock build itself differs by 0.02
# in ~384. The leftover is 0.08*(1 - h/w) units, four parts in 100,000 at 1080p,
# far under a single pixel. An absolute tolerance would call the correct case
# broken; 0.1% separates "square" from the 33% error this fix exists to remove.
SQUARE_TOL = 1e-3


class EmuError(RuntimeError):
    pass


class Image(object):
    """A PE mapped as flat memory, plus the bits of its header worth naming."""

    def __init__(self, path):
        self.path = path
        with open(path, "rb") as f:
            self.data = f.read()
        self.pe = sl_patch.parse_pe(self.data)
        self.image_base = self.pe["image_base"]
        e_lfanew = struct.unpack_from("<I", self.data, 0x3C)[0]
        opt = e_lfanew + 4 + 20
        self.entry = struct.unpack_from("<I", self.data, opt + 16)[0]
        self.size_of_image = struct.unpack_from("<I", self.data, opt + 56)[0]
        self.size_of_headers = struct.unpack_from("<I", self.data, opt + 60)[0]

    def sections(self):
        return self.pe["secs"]


class Machine(object):
    """One emulator instance holding one image. Reusable across calls."""

    def __init__(self, image, trace=False):
        if not HAVE_UNICORN:
            raise EmuError(
                "the 'unicorn' package is required for sl_emu\n"
                "  pip install unicorn        (see requirements-optional.txt)")
        self.image = image
        self.trace = trace
        self.writes = []          # (addr, size, value) for every store executed
        self.executed = 0
        self.uc = Uc(UC_ARCH_X86, UC_MODE_32)
        self._map_image()
        self._map_stack()
        self._hook()

    # ---- layout ------------------------------------------------------------
    def _map_image(self):
        base = self.image.image_base
        size = _align_up(max(self.image.size_of_image, PAGE))
        self.uc.mem_map(base, size)
        # headers first, then each section's raw bytes at its virtual address.
        # A section with less raw data than virtual size (.bss and friends) keeps
        # the zero fill the mapping already gives it, exactly as the loader would.
        self.uc.mem_write(base, self.image.data[:self.image.size_of_headers])
        for s in self.image.sections():
            raw = self.image.data[s["raw"]:s["raw"] + s["rawsize"]]
            if raw:
                self.uc.mem_write(base + s["va"], raw)
        self.base, self.size = base, size

    def _map_stack(self):
        self.uc.mem_map(STACK_BASE, STACK_SIZE)
        self.uc.mem_map(MAGIC_RET, PAGE)
        self.uc.mem_write(MAGIC_RET, b"\xc3")      # a lone ret, never reached

    def _hook(self):
        from unicorn import UC_HOOK_MEM_WRITE, UC_HOOK_CODE

        def on_write(uc, access, address, size, value, user):
            self.writes.append((address, size, value))

        def on_code(uc, address, size, user):
            self.executed += 1
            if self.trace:
                print("    %08X" % address)

        self.uc.hook_add(UC_HOOK_MEM_WRITE, on_write)
        self.uc.hook_add(UC_HOOK_CODE, on_code)

    # ---- memory ------------------------------------------------------------
    def read(self, va, n):
        return bytes(self.uc.mem_read(va, n))

    def read_u32(self, va):
        return struct.unpack("<I", self.read(va, 4))[0]

    def read_f32(self, va):
        return struct.unpack("<f", self.read(va, 4))[0]

    def write_u32(self, va, value):
        self.uc.mem_write(va, struct.pack("<I", value & 0xFFFFFFFF))

    def write_f32(self, va, value):
        self.uc.mem_write(va, struct.pack("<f", float(value)))

    # ---- execution ---------------------------------------------------------
    def call(self, va, args_f32=(), args_u32=(), allow=None, max_insns=200000):
        """Enter one function with a cdecl stack frame and stop when it leaves.

        Arguments are pushed right-to-left as 32-bit values, under a return
        address pointing at a page of its own, so a normal `ret` ends the run.

        `allow` is a list of (lo, hi) regions execution may stay inside; the run
        halts the moment it steps outside all of them. That is how a routine which
        calls other engine code gets measured without stubbing anything: whatever
        it computes before its first call has already happened. It takes a LIST
        rather than one range because a patched build jumps out to a code cave in
        the section slack, which is part of the function under test even though it
        is nowhere near it. Passing the caves in is what lets the same measurement
        run against a stock and a patched image and mean the same thing.
        """
        if allow and isinstance(allow[0], int):      # a bare (lo, hi) tuple
            allow = [tuple(allow)]
        from unicorn import UC_HOOK_CODE

        words = [struct.unpack("<I", struct.pack("<f", float(a)))[0] for a in args_f32]
        words += [int(a) & 0xFFFFFFFF for a in args_u32]

        esp = STACK_BASE + STACK_SIZE - 0x1000
        for w in reversed(words):
            esp -= 4
            self.uc.mem_write(esp, struct.pack("<I", w))
        esp -= 4
        self.uc.mem_write(esp, struct.pack("<I", MAGIC_RET))
        self.uc.reg_write(UC_X86_REG_ESP, esp)

        self.writes = []
        self.executed = 0
        left = {"at": None}

        h = None
        if allow:
            regions = [(int(lo), int(hi)) for lo, hi in allow]

            def guard(uc, address, size, user):
                for lo, hi in regions:
                    if lo <= address < hi:
                        return
                left["at"] = address
                uc.emu_stop()

            h = self.uc.hook_add(UC_HOOK_CODE, guard)
        try:
            self.uc.emu_start(va, MAGIC_RET, timeout=0, count=max_insns)
        except UcError as e:
            raise EmuError("emulation fault at EIP=0x%08X after %d instructions: %s"
                           % (self.uc.reg_read(UC_X86_REG_EIP), self.executed, e))
        finally:
            if h is not None:
                self.uc.hook_del(h)
        return dict(writes=list(self.writes), executed=self.executed,
                    left_at=left["at"])


# ================================================================= projection ==
def cave_regions(exe_path):
    """Code-cave (lo, hi) regions from the sidecar manifest sl_patch leaves.

    A patched build's hook is a JMP into slack elsewhere in .text. Without this
    the range guard would stop at the jump, the function would store nothing, and
    the comparison would silently read zeros as agreement.
    """
    man = sl_patch._read_manifest(exe_path)
    out = []
    if not man:
        return out
    for patch in man.get("patches", []):
        for cave in patch.get("caves", []):
            va = cave.get("va")
            n = len(cave.get("bytes", "")) // 2
            if va and n:
                out.append((va, va + n))
    return out


def probe_projection(exe_path, width, height, verbose=False):
    """Run the real projection writer at one resolution. -> dict of measurements.

    The device width/height globals are seeded exactly as the engine seeds them
    before the call, then the function itself decides what the scales become. The
    scale slots are poisoned with a sentinel first: if the run never stores to
    them the result is reported as "no store", never as a pair of equal zeros.
    """
    img = Image(exe_path)
    m = Machine(img, trace=verbose)
    m.write_u32(G_DEV_WIDTH, int(width))
    m.write_u32(G_DEV_HEIGHT, int(height))
    m.write_f32(G_SCALE_X, float("nan"))
    m.write_f32(G_SCALE_Y, float("nan"))

    allow = [(PROJ_FUNC, PROJ_END)] + cave_regions(exe_path)
    res = m.call(PROJ_FUNC, args_f32=PROJ_ARGS, allow=allow)

    touched = set(a for a, _s, _v in res["writes"])
    wrote = (G_SCALE_X in touched) and (G_SCALE_Y in touched)
    sx = m.read_f32(G_SCALE_X)
    sy = m.read_f32(G_SCALE_Y)
    return dict(
        exe=os.path.basename(exe_path), width=int(width), height=int(height),
        scale_x=sx, scale_y=sy, wrote=wrote,
        caves=len(allow) - 1,
        ratio=(sx / sy) if (wrote and sy) else float("nan"),
        square=(wrote and abs((sx / sy) - 1.0) <= SQUARE_TOL if (wrote and sy) else False),
        residual=(sx - sy) if wrote else float("nan"),
        insns=res["executed"], left_at=res["left_at"],
        writes=res["writes"],
    )


def _fmt(r):
    if not r["wrote"]:
        return ("  %-22s %5dx%-5d  *** NO STORE to the scale globals after %d "
                "instructions (left at %s) ***"
                % (r["exe"], r["width"], r["height"], r["insns"],
                   "0x%08X" % r["left_at"] if r["left_at"] else "its own ret"))
    return ("  %-22s %5dx%-5d  scale_x=%12.5f  scale_y=%12.5f  x/y=%8.5f  %s"
            % (r["exe"], r["width"], r["height"], r["scale_x"], r["scale_y"],
               r["ratio"], "SQUARE" if r["square"] else "stretched"))


def cmd_projection(args):
    for res in args.res:
        w, h = _parse_res(res)
        r = probe_projection(args.exe, w, h, verbose=args.verbose)
        print(_fmt(r))
        if args.verbose:
            print("      %d instructions, left the function at %s"
                  % (r["insns"], "0x%08X" % r["left_at"] if r["left_at"] else "its own ret"))
            for addr, size, value in r["writes"]:
                as_f = struct.unpack("<f", struct.pack("<I", value & 0xFFFFFFFF))[0] \
                    if size == 4 else None
                print("      store [%08X] %d = 0x%08X%s"
                      % (addr, size, value & 0xFFFFFFFF,
                         ("  (%.5f as float)" % as_f) if as_f is not None else ""))
    return 0


def cmd_compare(args):
    print("Projection scales, measured by executing FUN_004C3A60 out of each image.")
    print("Hor+ is correct when the patched build's x and y scales are EQUAL:")
    print("vertical field of view fixed, horizontal widened, pixels square.\n")
    bad = 0
    for res in args.res:
        w, h = _parse_res(res)
        a = probe_projection(args.stock, w, h)
        b = probe_projection(args.patched, w, h)
        print(_fmt(a))
        print(_fmt(b))
        if not (a["wrote"] and b["wrote"]):
            print("  -> UNMEASURED: one of the images stored nothing; "
                  "the comparison is void here.\n")
            bad += 1
            continue
        four_three = abs((w / float(h)) - 4.0 / 3.0) < 1e-6
        if four_three:
            same = (a["scale_x"] == b["scale_x"] and a["scale_y"] == b["scale_y"])
            print("  -> 4:3, so the patch must be a NO-OP here: %s"
                  % ("confirmed, identical" if same else "*** DIFFERS ***"))
            bad += 0 if same else 1
        else:
            print("  -> widescreen: patched scales equal? %s"
                  % ("yes" if b["square"] else "*** NO ***"))
            bad += 0 if b["square"] else 1
            if a["square"]:
                print("  -> NOTE: the stock build was already square here.")
        print("")
    print("verdict: %s" % ("every case behaved as the fix claims" if not bad
                           else "%d case(s) did NOT match the claim" % bad))
    return 1 if bad else 0


def cmd_call(args):
    img = Image(args.exe)
    m = Machine(img, trace=args.verbose)
    for item in args.u32 or []:
        va, _eq, val = item.partition("=")
        m.write_u32(int(va, 0), int(val, 0))
    va = int(args.va, 0)
    res = m.call(va, args_f32=[float(a) for a in (args.arg_f32 or [])],
                 args_u32=[int(a, 0) for a in (args.arg_u32 or [])],
                 allow=[(va, va + args.span)] + cave_regions(args.exe))
    print("entered 0x%08X, executed %d instructions, left at %s"
          % (va, res["executed"],
             "0x%08X" % res["left_at"] if res["left_at"] else "its own ret"))
    for addr, size, value in res["writes"]:
        as_f = struct.unpack("<f", struct.pack("<I", value & 0xFFFFFFFF))[0] \
            if size == 4 else None
        print("  store [%08X] %d = 0x%08X%s"
              % (addr, size, value & 0xFFFFFFFF,
                 ("  (%.5f as float)" % as_f) if as_f is not None else ""))
    return 0


def _parse_res(text):
    w, h = text.lower().replace(" ", "").split("x")
    return int(w), int(h)


# =================================================================== selftest ==
def selftest():
    """Prove the machine works on a SYNTHETIC program, with no game image.

    The point is that the harness itself is trustworthy: a hand-assembled function
    is emulated and its arithmetic and stores are checked. Runs anywhere unicorn
    is installed, on any platform, and touches nothing belonging to the game.
    """
    fails = []
    ran = [0]

    def check(cond, label):
        ran[0] += 1
        print("  %-4s %s" % ("ok" if cond else "FAIL", label))
        if not cond:
            fails.append(label)

    print("=== sl_emu self-test (synthetic program, no game image) ===")
    if not HAVE_UNICORN:
        print("  SKIP unicorn is not installed; sl_emu is an optional tool")
        return 0

    # a synthetic PE carrying one function:
    #   mov eax,[esp+4]      ; first cdecl argument
    #   add eax,[esp+8]      ; plus the second
    #   mov [0x00402000],eax ; store the sum
    #   ret
    code = bytes.fromhex("8b442404" "03442408" "a300204000" "c3")
    base, code_rva, data_rva = 0x00400000, 0x1000, 0x2000

    def build():
        e_lfanew, opt_size, nsec = 0x80, 0xE0, 2
        buf = bytearray(b"\x00" * 0x400)
        buf[0:2] = b"MZ"
        struct.pack_into("<I", buf, 0x3C, e_lfanew)
        buf[e_lfanew:e_lfanew + 4] = b"PE\x00\x00"
        coff = e_lfanew + 4
        struct.pack_into("<H", buf, coff + 2, nsec)
        struct.pack_into("<H", buf, coff + 16, opt_size)
        opt = coff + 20
        struct.pack_into("<I", buf, opt + 16, code_rva)      # entry point
        struct.pack_into("<I", buf, opt + 28, base)          # image base
        struct.pack_into("<I", buf, opt + 56, 0x4000)        # size of image
        struct.pack_into("<I", buf, opt + 60, 0x400)         # size of headers
        tbl = opt + opt_size
        for i, (nm, rva, raw, rawsize) in enumerate(
                ((".text", code_rva, 0x400, 0x200), (".data", data_rva, 0x600, 0x200))):
            o = tbl + i * 40
            buf[o:o + len(nm)] = nm.encode()
            struct.pack_into("<IIII", buf, o + 8, 0x200, rva, rawsize, raw)
            struct.pack_into("<I", buf, o + 36, 0x60000020)
        buf += b"\x00" * 0x200                                # .text raw @ 0x400
        buf[0x400:0x400 + len(code)] = code
        buf += b"\x00" * 0x200                                # .data raw @ 0x600
        return bytes(buf)

    import tempfile
    fd, path = tempfile.mkstemp(suffix=".exe", prefix="slemu_")
    os.close(fd)
    try:
        with open(path, "wb") as f:
            f.write(build())
        img = Image(path)
        check(img.image_base == base, "PE header: image base read back")
        check(img.size_of_image == 0x4000, "PE header: size of image read back")

        m = Machine(img)
        target = base + code_rva
        res = m.call(target, args_u32=(7, 35), allow=[(target, target + 0x40)])
        check(m.read_u32(base + data_rva) == 42,
              "executed: 7 + 35 stored as 42 at the target global")
        check(res["executed"] == 4, "executed: exactly the 4 instructions of the function")
        check(res["left_at"] is None, "executed: ended on its own ret, not by leaving")
        check((base + data_rva, 4, 42) in res["writes"], "store hook: the write was recorded")

        res = m.call(target, args_u32=(1, 1), allow=[(target, target + 0x40)])
        check(m.read_u32(base + data_rva) == 2, "reusable: a second call re-runs cleanly")
        check(len(res["writes"]) == 1, "reusable: the write log resets per call")

        # leaving the declared range must stop the run rather than wander off
        res2 = m.call(target, args_u32=(1, 1), allow=[(target, target + 4)])
        check(res2["left_at"] is not None, "range guard: halts when execution leaves")

        floats = [struct.unpack("<I", struct.pack("<f", v))[0] for v in (1.5, 2.5)]
        m.call(target, args_u32=floats, allow=[(target, target + 0x40)])
        check(m.read_u32(base + data_rva) == (floats[0] + floats[1]) & 0xFFFFFFFF,
              "arguments: cdecl words arrive in order at [esp+4], [esp+8]")
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass

    print("sl_emu self-test: %d checks, %d failed" % (ran[0], len(fails)))
    for f in fails:
        print("  FAILED: " + f)
    return 1 if fails else 0


# ======================================================================== CLI ==
def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Execute one function out of the Starlancer image in an emulator. "
                    "The game is never launched.")
    sub = ap.add_subparsers(dest="cmd")

    p = sub.add_parser("projection", help="measure FUN_004C3A60's projection scales")
    p.add_argument("exe")
    p.add_argument("--res", nargs="+", default=["1920x1080"])
    p.add_argument("--verbose", action="store_true")
    p.set_defaults(func=cmd_projection)

    p = sub.add_parser("compare", help="stock vs patched, at several resolutions")
    p.add_argument("stock")
    p.add_argument("patched")
    p.add_argument("--res", nargs="+",
                   default=["640x480", "1024x768", "1920x1080", "2560x1080", "3440x1440"])
    p.set_defaults(func=cmd_compare)

    p = sub.add_parser("call", help="enter an arbitrary function and log its stores")
    p.add_argument("exe")
    p.add_argument("va")
    p.add_argument("--arg-f32", nargs="*")
    p.add_argument("--arg-u32", nargs="*")
    p.add_argument("--u32", nargs="*", help="seed memory, e.g. 0x5e81b6=1920")
    p.add_argument("--span", type=lambda x: int(x, 0), default=0x400)
    p.add_argument("--verbose", action="store_true")
    p.set_defaults(func=cmd_call)

    p = sub.add_parser("selftest", help="verify the harness on a synthetic program")
    p.set_defaults(func=lambda a: selftest())

    args = ap.parse_args(argv)
    if not getattr(args, "func", None):
        ap.print_help()
        return 2
    try:
        return args.func(args)
    except EmuError as e:
        print("error: %s" % e, file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
