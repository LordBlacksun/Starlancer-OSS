#!/usr/bin/env python3
"""
pe_inspect.py - read-only PE32 inspector + SafeDisc fingerprinter.

Part of the Starlancer RE project. Parses a Windows PE (no third-party deps),
prints DOS/COFF/Optional headers, the section table with Shannon entropy
(high entropy ~8.0 == encrypted/packed), the import DLL list, the TLS
directory, and scans for SafeDisc copy-protection markers + version.

NEVER executes the target. Pure file read. Usage:
    python pe_inspect.py <file.exe|file.icd> [more files...]
"""
import sys, struct, math

SAFEDISC_MARKERS = [
    b"BoG_ *90.0&!!  Yy>",        # canonical SafeDisc product signature (PEiD)
    b"SafeDisc", b"Macrovision", b"C-Dilla",
    b"DRVMGT", b"drvmgt", b"secdrv", b"CLOKSPL", b"CLCD16", b"CLCD32",
    b"~e0017.", b"stxt371", b"stxt774", b"DPLAYERX",
]

def entropy(b: bytes) -> float:
    if not b:
        return 0.0
    counts = [0]*256
    for x in b:
        counts[x] += 1
    n = len(b)
    h = 0.0
    for c in counts:
        if c:
            p = c/n
            h -= p*math.log2(p)
    return h

def rva_to_off(rva, sections):
    for s in sections:
        va, vs, raw, rs = s['va'], max(s['vsize'], s['rawsize']), s['raw'], s['rawsize']
        if va <= rva < va+vs:
            return raw + (rva-va)
    return None

def cstr(data, off, maxlen=64):
    end = data.find(b"\x00", off)
    if end < 0 or end-off > maxlen:
        end = off+maxlen
    return data[off:end].decode("latin-1", "replace")

def inspect(path):
    with open(path, "rb") as f:
        data = f.read()
    print(f"\n{'='*78}\nFILE: {path}\n  size: {len(data):,} bytes\n{'='*78}")
    if data[:2] != b"MZ":
        print("  !! not an MZ image"); return
    e_lfanew = struct.unpack_from("<I", data, 0x3C)[0]
    if data[e_lfanew:e_lfanew+4] != b"PE\x00\x00":
        print(f"  !! no PE header at e_lfanew=0x{e_lfanew:X}"); return
    coff = e_lfanew+4
    (machine, nsec, tds, _psym, _nsym, opt_size, chars) = struct.unpack_from("<HHIIIHH", data, coff)
    opt = coff+20
    magic = struct.unpack_from("<H", data, opt)[0]
    pe_plus = (magic == 0x20b)
    print(f"  Machine: 0x{machine:04X} ({'x86' if machine==0x14c else 'x64' if machine==0x8664 else '?'})"
          f"   Sections: {nsec}   OptMagic: 0x{magic:X} ({'PE32+' if pe_plus else 'PE32'})")
    aoe, base_of_code = struct.unpack_from("<II", data, opt+16)
    if pe_plus:
        image_base = struct.unpack_from("<Q", data, opt+24)[0]
    else:
        image_base = struct.unpack_from("<I", data, opt+28)[0]
    sect_align, file_align = struct.unpack_from("<II", data, opt+32)
    size_of_image = struct.unpack_from("<I", data, opt+56)[0]
    size_of_hdrs  = struct.unpack_from("<I", data, opt+60)[0]
    subsystem = struct.unpack_from("<H", data, opt+68)[0]
    print(f"  ImageBase: 0x{image_base:08X}   EntryPoint(RVA): 0x{aoe:08X} -> VA 0x{image_base+aoe:08X}")
    print(f"  SizeOfImage: 0x{size_of_image:X}   SizeOfHeaders: 0x{size_of_hdrs:X}   Subsystem: {subsystem}"
          f" ({'GUI' if subsystem==2 else 'CUI' if subsystem==3 else '?'})")
    # data directories
    dd_off = opt + (112 if pe_plus else 96)
    ndd = struct.unpack_from("<I", data, opt+(108 if pe_plus else 92))[0]
    dirs = [struct.unpack_from("<II", data, dd_off+i*8) for i in range(min(ndd,16))]
    DD_NAMES = ["Export","Import","Resource","Exception","Security","BaseReloc","Debug","Arch",
                "GlobalPtr","TLS","LoadConfig","BoundImport","IAT","DelayImport","CLR","Reserved"]
    # sections
    sect_tbl = opt + opt_size
    sections = []
    print(f"\n  {'Name':<9} {'VirtAddr':>10} {'VirtSize':>10} {'RawPtr':>10} {'RawSize':>10} {'Flags':>10} {'Entropy':>8}")
    for i in range(nsec):
        o = sect_tbl + i*40
        name = data[o:o+8].rstrip(b"\x00").decode("latin-1","replace")
        vsize, va, rawsize, raw = struct.unpack_from("<IIII", data, o+8)
        flags = struct.unpack_from("<I", data, o+36)[0]
        body = data[raw:raw+rawsize]
        ent = entropy(body)
        sections.append({'name':name,'va':va,'vsize':vsize,'raw':raw,'rawsize':rawsize,'flags':flags,'ent':ent})
        exec_flag = 'X' if flags & 0x20000000 else ' '
        write_flag = 'W' if flags & 0x80000000 else ' '
        hot = '  <== HIGH ENTROPY (encrypted/packed?)' if ent > 7.2 else ''
        print(f"  {name:<9} 0x{va:08X} 0x{vsize:08X} 0x{raw:08X} 0x{rawsize:08X} 0x{flags:08X} {ent:7.3f} {exec_flag}{write_flag}{hot}")
        # which section holds the entry point?
        if va <= aoe < va+max(vsize,rawsize):
            print(f"            ^^ ENTRY POINT is in section '{name}'")
    # data dirs of interest
    print("\n  Data directories (non-empty):")
    for i,(rva,sz) in enumerate(dirs):
        if rva or sz:
            nm = DD_NAMES[i] if i < len(DD_NAMES) else str(i)
            print(f"    {nm:<12} RVA=0x{rva:08X} size=0x{sz:X}")
    # imports
    if len(dirs) > 1 and dirs[1][0]:
        imp_off = rva_to_off(dirs[1][0], sections)
        if imp_off is not None:
            print("\n  Imported DLLs:")
            k = 0
            while True:
                ent_off = imp_off + k*20
                fields = struct.unpack_from("<IIIII", data, ent_off)
                if fields == (0,0,0,0,0) or all(v==0 for v in fields):
                    break
                name_rva = fields[3]
                no = rva_to_off(name_rva, sections)
                dll = cstr(data, no) if no is not None else f"<rva 0x{name_rva:X} unmapped>"
                print(f"    - {dll}")
                k += 1
                if k > 100: break
        else:
            print("\n  Import directory RVA not mapped to a section (table may be built at runtime / encrypted).")
    # TLS
    if len(dirs) > 9 and dirs[9][0]:
        print(f"\n  !! TLS directory present (RVA=0x{dirs[9][0]:08X}) - SafeDisc often uses a TLS callback.")
    # SafeDisc markers
    print("\n  SafeDisc / protection markers:")
    found_any = False
    for m in SAFEDISC_MARKERS:
        idx = data.find(m)
        if idx >= 0:
            found_any = True
            extra = ""
            if m == b"BoG_ *90.0&!!  Yy>":
                # version DWORDs immediately follow the signature
                vbytes = data[idx+len(m):idx+len(m)+12]
                if len(vbytes) == 12:
                    a,b2,c = struct.unpack("<III", vbytes)
                    extra = f"   => SafeDisc version {a}.{b2:02d}.{c:03d} (build)"
            print(f"    FOUND @0x{idx:08X}: {m!r}{extra}")
    if not found_any:
        print("    (none of the known markers found)")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__); sys.exit(1)
    for p in sys.argv[1:]:
        try:
            inspect(p)
        except Exception as e:
            print(f"  ERROR inspecting {p}: {e!r}")
