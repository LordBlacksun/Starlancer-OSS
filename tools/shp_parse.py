#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 LordBlacksun
# SPDX-License-Identifier: GPL-3.0-only
"""Starlancer ``.SHP`` 3D-model decoder  (READ-ONLY, static, standard library only).

A ``.SHP`` ("sro_file" in the engine's own strings, ``C:\\lancer\\game\\srofiles.cpp``)
is a **RefPack-compressed stream of tagged chunks** -- see ``docs/shp-format.md`` for the
full specification and the evidence behind every field.  Nothing here executes game code:
the file is opened as bytes, decompressed with the project's clean-room RefPack decoder
(shared with ``dte_parse.py``) and walked exactly the way the game's loader
``FUN_004A44D0`` walks it (chunk reader ``FUN_004A2EB0``: search forward for a tag,
leave the cursor alone on a miss).

Container (verified against the decrypted exe and all 435 shipped models):

* ``10 FB`` + 3-byte big-endian image size, then the RefPack stream.
* The image is a flat sequence of chunks ``{u16 tag, u16 record_size, u16 count}`` followed
  by ``count * record_size`` bytes, terminated by tag ``0xFFFF``.  Record sizes are the
  format's version mechanism: the loader copies ``min(record_size, struct_size)`` bytes of
  each record into a fixed in-memory struct, so older files simply carry shorter records.
* Chunk order = the loader's request order: header (0), parts (1); then per part: LOD list
  (2), nodes (7), attachments (9), animation clips (0xA), groups (0xD), trigger polygons
  (0xF); per LOD: vertices (4), faces (3), materials (6); per node: face-index list (8);
  per clip: keyframes (0xB), events (0xC); per group: entries (0xE); then the model-level
  tail (0x10).  A chunk the exporter did not emit is skipped by the search-forward rule.

Usage:
  shp_parse.py info   <model.shp>                 # chunk walk: tag / record size / count
  shp_parse.py tree   <model.shp>                 # parts -> LODs, attachments, clips, ...
  shp_parse.py dump   <model.shp> --tag 9 [-n 20] # typed record dump for one chunk tag
  shp_parse.py obj    <model.shp> -o out.obj      # Wavefront OBJ of one LOD (default 0)
  shp_parse.py sweep  <dir>                       # decode + validate every .shp in a folder
  shp_parse.py --selftest                         # synthetic round-trip, no game data needed

Game data is never committed to the repo; run these against your own extracted files
(``hog_extract.py resource.hog -o <dir>``).
"""
import argparse
import collections
import glob
import math
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from dte_parse import refpack_decompress            # noqa: E402  (project RefPack decoder)
except ImportError:                                      # pragma: no cover
    refpack_decompress = None


class SHPError(Exception):
    """Malformed or truncated .SHP input (never a crash: callers print the message)."""


# --------------------------------------------------------------------------- #
#  Chunk catalogue -- tag -> (name, in-memory struct size in the engine).       #
#  The in-memory size is what the loader passes to the chunk reader; the file  #
#  record size is whatever the exporter wrote (several versions ship).         #
# --------------------------------------------------------------------------- #
TAG_HEADER, TAG_PART, TAG_LOD, TAG_FACE, TAG_VERTEX, TAG_MATERIAL = 0, 1, 2, 3, 4, 6
TAG_NODE, TAG_NODE_FACES, TAG_ATTACH, TAG_CLIP, TAG_KEY, TAG_EVENT = 7, 8, 9, 0xA, 0xB, 0xC
TAG_GROUP, TAG_GROUP_ENTRY, TAG_TRIGGER_POLY, TAG_TAIL, TAG_END = 0xD, 0xE, 0xF, 0x10, 0xFFFF

TAGS = {
    TAG_HEADER:       ("header",          0x68),
    TAG_PART:         ("part",            0x258),
    TAG_LOD:          ("lod",             0x1C),
    TAG_FACE:         ("face",            0x50),
    TAG_VERTEX:       ("vertex",          0x20),
    TAG_MATERIAL:     ("material",        0x48),
    TAG_NODE:         ("node",            0x5C),
    TAG_NODE_FACES:   ("node-faces",      0x04),
    TAG_ATTACH:       ("attachment",      0x7C),
    TAG_CLIP:         ("clip",            0x28),
    TAG_KEY:          ("keyframe",        0x1C),
    TAG_EVENT:        ("event",           0x0C),
    TAG_GROUP:        ("group",           0x0C),
    TAG_GROUP_ENTRY:  ("group-entry",     0x14),
    TAG_TRIGGER_POLY: ("trigger-polygon", 0x54),
    TAG_TAIL:         ("tail",            0x4C),
}

# Attachment (tag 9) type codes.  VERIFIED = a game function tests for that value;
# INFERRED = placement/occurrence only (see docs/shp-format.md section 5.9).
ATTACH_TYPES = {
    0: "gun hardpoint",            # verified: FUN_0045E1A0 / FUN_0045E500 (gun creation)
    1: "turret mount?",            # inferred: capital ships only
    2: "engine effect",            # verified: FUN_004924B0 -> FUN_00494400
    3: "muzzle / launch point?",   # inferred: gun barrel tip; two forward points on fighters
    4: "light",                    # verified: FUN_004A4310 / FUN_004A4130 (static-light bake)
    5: "unknown (capital ships)",
    6: "cockpit view point?",      # inferred: exactly one per fighter, on the cockpit part
    7: "effect emitter",           # verified: FUN_0047C800 (animation event kind 2)
    8: "unknown (carriers)",
    9: "docking point",            # verified: FUN_00406C80 (aidock.cpp)
}

# Part type codes (part +0x40).  Labels come from the parts' own names; the engine
# verifiably tests 1, 6 and the turret set {3, 9, 10, 18} (docs section 5.2).
PART_TYPES = {
    0: "generic / hull", 1: "destructible section", 2: "cockpit", 3: "turret base",
    5: "engine", 6: "shield generator", 7: "comms", 8: "grav panel", 9: "turret (unnamed)",
    10: "turret (unnamed)", 11: "core / module", 12: "comm dish", 13: "door / panel",
    14: "exhaust", 15: "projector generator", 16: "core element", 17: "cover / duct entrance",
    18: "ion cannon", 19: "panel", 22: "cargo pod",
}

CLIP_MODES = {0: "none", 1: "once", 2: "loop", 3: "ping-pong"}


# --------------------------------------------------------------------------- #
#  Low-level: decompress + chunk walk                                          #
# --------------------------------------------------------------------------- #
def load_image(raw):
    """RefPack-decode a .SHP blob -> image bytes.  Raises SHPError on bad input."""
    if refpack_decompress is None:
        raise SHPError("dte_parse.py (RefPack decoder) not found next to this script")
    if len(raw) < 6 or raw[1] != 0xFB:
        raise SHPError("not a RefPack stream (first bytes %s)" % raw[:2].hex())
    try:
        declared, img = refpack_decompress(raw)
    except Exception as e:                      # dte_parse raises its own error type
        raise SHPError("RefPack decode failed: %s" % e)
    if declared != len(img):
        raise SHPError("RefPack size mismatch: header says %d, produced %d" % (declared, len(img)))
    return img


def walk_chunks(img):
    """Yield (index, tag, record_size, count, data_offset) for every chunk up to the
    0xFFFF terminator.  Raises SHPError if a chunk overruns the image or no terminator."""
    p, k = 0, 0
    while True:
        if p + 6 > len(img):
            raise SHPError("no 0xFFFF terminator (ran off the image at %#x)" % p)
        tag, esz, cnt = struct.unpack_from("<HHH", img, p)
        if tag == TAG_END:
            if p + 6 != len(img):
                raise SHPError("%d trailing byte(s) after the terminator" % (len(img) - p - 6))
            return
        end = p + 6 + esz * cnt
        if end > len(img):
            raise SHPError("chunk %d (tag %#x) overruns the image (%d > %d)" % (k, tag, end, len(img)))
        yield k, tag, esz, cnt, p + 6
        p, k = end, k + 1


class Cursor:
    """The engine's chunk reader: search forward for `tag`; on a miss return None and keep
    the cursor; on a hit consume the chunk and return its records."""

    def __init__(self, img):
        self.chunks = list(walk_chunks(img))
        self.img = img
        self.pos = 0

    def take(self, tag):
        i = self.pos
        while i < len(self.chunks) and self.chunks[i][1] != tag:
            i += 1
        if i >= len(self.chunks):
            return None
        _, _, esz, cnt, off = self.chunks[i]
        self.pos = i + 1
        return [self.img[off + j * esz: off + (j + 1) * esz] for j in range(cnt)], esz


# --------------------------------------------------------------------------- #
#  Record decoders (field offsets per docs/shp-format.md).  Fields that lie    #
#  beyond a short (older) record are reported as None.                         #
# --------------------------------------------------------------------------- #
def _u32(b, o):
    return struct.unpack_from("<I", b, o)[0] if o + 4 <= len(b) else None


def _i32(b, o):
    return struct.unpack_from("<i", b, o)[0] if o + 4 <= len(b) else None


def _u16(b, o):
    return struct.unpack_from("<H", b, o)[0] if o + 2 <= len(b) else None


def _f32(b, o):
    return struct.unpack_from("<f", b, o)[0] if o + 4 <= len(b) else None


def _vec3(b, o):
    return struct.unpack_from("<3f", b, o) if o + 12 <= len(b) else None


def _mat3(b, o):
    return struct.unpack_from("<9f", b, o) if o + 36 <= len(b) else None


def _cstr(b, o, n):
    s = b[o:o + n]
    return s.split(b"\0")[0].decode("latin-1", "replace")


def dec_header(b):
    return {"magic": _u32(b, 0), "f_04": _f32(b, 4), "vec_08": _vec3(b, 8), "flags": _u32(b, 0x14)}


def dec_part(b):
    return {
        "name": _cstr(b, 0, 64), "type": _u32(b, 0x40), "position": _vec3(b, 0x44),
        "bbox_min": _vec3(b, 0x50), "bbox_max": _vec3(b, 0x5C), "parent": _i32(b, 0x94),
        "mount": _vec3(b, 0x98), "matrix": _mat3(b, 0xA4), "link_id": _u32(b, 0xD4),
        "yaw_min": _f32(b, 0xD8), "pitch_min": _f32(b, 0xDC), "f_e0": _f32(b, 0xE0),
        "yaw_max": _f32(b, 0xE4), "pitch_max": _f32(b, 0xE8), "f_ec": _f32(b, 0xEC),
        "flags": _u32(b, 0xF0), "turret_kind": _u32(b, 0xF4), "u_f8": _u32(b, 0xF8),
    }


def dec_vertex(b):
    return {"position": _vec3(b, 0), "normal": _vec3(b, 0xC), "u_18": _u32(b, 0x18),
            "next_lod_index": _i32(b, 0x1C)}


def dec_face(b):
    d = struct.unpack_from("<%dI" % (len(b) // 4), b, 0)
    g = lambda i: d[i] if i < len(d) else None
    f = lambda i: struct.unpack_from("<f", b, i * 4)[0] if i < len(d) else None
    return {
        "material": g(0), "mode": (g(1) or 0) & 0xF, "submode": ((g(1) or 0) >> 4) & 0xF,
        "flags": g(2), "v": (g(3), g(4), g(5)), "u": (f(6), f(7), f(8)), "vt": (f(9), f(10), f(11)),
        "normal": (f(12), f(13), f(14)), "u_0f": g(15), "f_10": f(16), "edge_mask": g(17),
        "poly_kind": g(18), "poly_rest": g(19),
    }


def dec_material(b):
    return {"name": _cstr(b, 0, 64)}


def dec_node(b):
    return {"u_00": _u32(b, 0), "matrix": _mat3(b, 4), "vec_28": _vec3(b, 0x28),
            "vec_34": _vec3(b, 0x34), "child_a": _i32(b, 0x40), "child_b": _i32(b, 0x44)}


def dec_attach(b):
    n = len(b) // 4
    d = struct.unpack_from("<%dI" % n, b, 0)
    g = lambda i: d[i] if i < n else None
    return {
        "type": g(0), "position": _vec3(b, 4), "matrix": _mat3(b, 0x10),
        "p13": (g(0xD), g(0xE), g(0xF), g(0x10)), "p11": g(0x11),
        "size": (_f32(b, 0x48), _f32(b, 0x4C)), "f14": _f32(b, 0x50),
        "blink": (g(0x15), g(0x16)), "p17": g(0x17), "p18": g(0x18), "p19": g(0x19),
        "range": _f32(b, 0x74), "intensity": _f32(b, 0x78),
    }


def dec_clip(b):
    return {"length": _u16(b, 0), "u_02": _u16(b, 2), "mode": _u16(b, 4),
            "name": _cstr(b, 6, 18) if len(b) >= 24 else ""}


def dec_key(b):
    return {"time": _i32(b, 0), "rotation": _vec3(b, 4), "translation": _vec3(b, 0x10)}


def dec_event(b):
    return {"time": _i32(b, 0), "kind": _u32(b, 4), "u_08": _u32(b, 8)}


def dec_group_entry(b):
    return {"u_00": _u32(b, 0), "face": _u32(b, 4), "position": _vec3(b, 8)}


def dec_poly(b):
    return {"v": tuple(struct.unpack_from("<4i", b, 0)) if len(b) >= 16 else None}


def dec_tail(b):
    return {"direction": _vec3(b, 0),
            "words": struct.unpack_from("<32h", b, 12) if len(b) >= 76 else None}


DECODERS = {
    TAG_HEADER: dec_header, TAG_PART: dec_part, TAG_VERTEX: dec_vertex, TAG_FACE: dec_face,
    TAG_MATERIAL: dec_material, TAG_NODE: dec_node, TAG_ATTACH: dec_attach, TAG_CLIP: dec_clip,
    TAG_KEY: dec_key, TAG_EVENT: dec_event, TAG_GROUP_ENTRY: dec_group_entry,
    TAG_TRIGGER_POLY: dec_poly, TAG_TAIL: dec_tail,
    TAG_LOD: lambda b: {"distance": _f32(b, 0)},
    TAG_NODE_FACES: lambda b: {"face": _u32(b, 0)},
    TAG_GROUP: lambda b: {"class": _u32(b, 0)},
}


# --------------------------------------------------------------------------- #
#  Model = the loader's structure assignment                                    #
# --------------------------------------------------------------------------- #
class Model:
    """Decoded .SHP: header, parts (each with lods/nodes/attachments/clips/groups/polys),
    tail.  Built with the engine's own search-forward chunk consumption so the assignment
    of chunks to parts/LODs/nodes matches what the game does."""

    def __init__(self, raw, name="?"):
        self.name = name
        self.raw_size = len(raw)
        self.img = load_image(raw)
        cur = Cursor(self.img)
        self.chunks = cur.chunks
        self.sizes = collections.defaultdict(set)
        for _, tag, esz, cnt, _ in self.chunks:
            self.sizes[tag].add(esz)

        hdr = cur.take(TAG_HEADER)
        if not hdr or not hdr[0]:
            raise SHPError("missing header chunk (tag 0)")
        self.header = dec_header(hdr[0][0])
        self.header_size = hdr[1]

        parts = cur.take(TAG_PART)
        self.parts = []
        for pb in (parts[0] if parts else []):
            part = dec_part(pb)
            part["record_size"] = parts[1]
            lods = cur.take(TAG_LOD)
            part["lods"] = [{"distance": _f32(b, 0), "vertices": [], "faces": [], "materials": [],
                             "vertex_size": None, "face_size": None} for b in (lods[0] if lods else [])]
            nodes = cur.take(TAG_NODE)
            part["nodes"] = [dict(dec_node(b), faces=[]) for b in (nodes[0] if nodes else [])]
            att = cur.take(TAG_ATTACH)
            part["attachments"] = [dict(dec_attach(b), record_size=att[1]) for b in (att[0] if att else [])]
            clips = cur.take(TAG_CLIP)
            part["clips"] = [dict(dec_clip(b), keys=[], events=[]) for b in (clips[0] if clips else [])]
            groups = cur.take(TAG_GROUP)
            part["groups"] = [{"class": _u32(b, 0), "entries": []} for b in (groups[0] if groups else [])]
            polys = cur.take(TAG_TRIGGER_POLY)
            part["trigger_polys"] = [dec_poly(b) for b in (polys[0] if polys else [])]
            for lod in part["lods"]:
                v = cur.take(TAG_VERTEX)
                if v:
                    lod["vertices"] = [dec_vertex(b) for b in v[0]]
                    lod["vertex_size"] = v[1]
                f = cur.take(TAG_FACE)
                if f:
                    lod["faces"] = [dec_face(b) for b in f[0]]
                    lod["face_size"] = f[1]
                m = cur.take(TAG_MATERIAL)
                if m:
                    lod["materials"] = [dec_material(b) for b in m[0]]
            for node in part["nodes"]:
                nf = cur.take(TAG_NODE_FACES)
                if nf:
                    node["faces"] = [_u32(b, 0) for b in nf[0]]
            for clip in part["clips"]:
                kk = cur.take(TAG_KEY)
                if kk:
                    clip["keys"] = [dec_key(b) for b in kk[0]]
                ev = cur.take(TAG_EVENT)
                if ev:
                    clip["events"] = [dec_event(b) for b in ev[0]]
            for grp in part["groups"]:
                ge = cur.take(TAG_GROUP_ENTRY)
                if ge:
                    grp["entries"] = [dec_group_entry(b) for b in ge[0]]
            self.parts.append(part)
        tail = cur.take(TAG_TAIL)
        self.tail = [dec_tail(b) for b in (tail[0] if tail else [])]

    # -- validation --------------------------------------------------------- #
    def validate(self):
        """Structural invariants the engine relies on.  Returns a list of problem strings."""
        bad = []
        npart = len(self.parts)
        for pi, part in enumerate(self.parts):
            pp = part["parent"]
            if pp is not None and not (pp == -1 or (0 <= pp < npart and pp != pi)):
                bad.append("part %d: parent index %d out of range" % (pi, pp))
            lods = part["lods"]
            for li, lod in enumerate(lods):
                nv = len(lod["vertices"])
                nxt = len(lods[li + 1]["vertices"]) if li + 1 < len(lods) else None
                for fi, f in enumerate(lod["faces"]):
                    if any(v is None or v >= nv for v in f["v"]):
                        bad.append("part %d lod %d face %d: vertex index >= %d" % (pi, li, fi, nv))
                        break
                    if f["material"] is not None and f["material"] >= max(1, len(lod["materials"])):
                        bad.append("part %d lod %d face %d: material %d out of range" % (pi, li, fi, f["material"]))
                        break
                if nxt is not None and (part["flags"] or 0) & 0x30:
                    # -1 = "no counterpart" (four shipped models carry it on tiny LODs)
                    for vi, v in enumerate(lod["vertices"]):
                        ix = v["next_lod_index"]
                        if ix is not None and not (-1 <= ix < nxt):
                            bad.append("part %d lod %d vertex %d: next-LOD index %d >= %d" % (pi, li, vi, ix, nxt))
                            break
            nf0 = len(lods[0]["faces"]) if lods else 0
            nv0 = len(lods[0]["vertices"]) if lods else 0
            for ni, node in enumerate(part["nodes"]):
                for key in ("child_a", "child_b"):
                    c = node[key]
                    if c is not None and not (c == -1 or 0 <= c < len(part["nodes"])):
                        bad.append("part %d node %d: %s=%d out of range" % (pi, ni, key, c))
                if any(fx >= nf0 for fx in node["faces"]):
                    bad.append("part %d node %d: face index >= %d" % (pi, ni, nf0))
            for ai, a in enumerate(part["attachments"]):
                if a["type"] is None or a["type"] > 9:
                    bad.append("part %d attachment %d: unknown type %r" % (pi, ai, a["type"]))
            for gi, g in enumerate(part["groups"]):
                if any(e["face"] is not None and e["face"] >= nf0 for e in g["entries"]):
                    bad.append("part %d group %d: entry face index >= %d" % (pi, gi, nf0))
            for qi, q in enumerate(part["trigger_polys"]):
                if q["v"] is None or any(v >= nv0 or v < -1 for v in q["v"]):
                    bad.append("part %d trigger-polygon %d: vertex index out of range" % (pi, qi))
        return bad


# --------------------------------------------------------------------------- #
#  Presentation helpers                                                         #
# --------------------------------------------------------------------------- #
def fv(v, nd=1):
    if v is None:
        return "-"
    return "(" + ", ".join("%.*f" % (nd, x) for x in v) + ")"


def cell(b, i):
    """Best-effort rendering of one dword: int / float / text."""
    u, = struct.unpack_from("<I", b, i)
    f, = struct.unpack_from("<f", b, i)
    s = b[i:i + 4]
    if u == 0:
        return "0"
    if u == 0xFFFFFFFF:
        return "-1"
    if all(32 <= c < 127 or c == 0 for c in s) and any(32 <= c < 127 for c in s) and not (1e-3 < abs(f) < 1e5):
        return repr(s.rstrip(b"\0").decode("latin-1"))
    if 1e-5 < abs(f) < 1e7:
        return "%.4g" % f
    if u < 100000:
        return str(u)
    if u >= 0xFFFF0000:
        return str(struct.unpack_from("<i", b, i)[0])
    return "0x%x" % u


def read_model(path):
    with open(path, "rb") as fh:
        raw = fh.read()
    return Model(raw, os.path.basename(path))


# --------------------------------------------------------------------------- #
#  Commands                                                                     #
# --------------------------------------------------------------------------- #
def cmd_info(args):
    m = read_model(args.file)
    print("%s: packed %d B -> image %d B, %d chunks" % (m.name, m.raw_size, len(m.img), len(m.chunks)))
    for k, tag, esz, cnt, off in m.chunks:
        nm = TAGS.get(tag, ("?", 0))[0]
        print("  [%3d] @%06x  tag %02x %-16s size %3d  count %5d" % (k, off - 6, tag, nm, esz, cnt))
    print("  terminator FFFF at %#x" % (len(m.img) - 6))


def cmd_tree(args):
    m = read_model(args.file)
    h = m.header
    print("%s  (image %d B, header record %d B, magic %s, flags %#x)"
          % (m.name, len(m.img), m.header_size, h["magic"], h["flags"] or 0))
    for pi, p in enumerate(m.parts):
        print("part %d %r  type %s (%s)  parent %s  link %s  flags %#x  turret-kind %s"
              % (pi, p["name"], p["type"], PART_TYPES.get(p["type"], "?"), p["parent"], p["link_id"],
                 p["flags"] or 0, p["turret_kind"]))
        print("   position %s  bbox %s .. %s  mount %s" % (fv(p["position"]), fv(p["bbox_min"]), fv(p["bbox_max"]), fv(p["mount"])))
        if p["yaw_min"] is not None and any(x for x in (p["yaw_min"], p["yaw_max"], p["pitch_min"], p["pitch_max"])):
            print("   turret limits: yaw [%g, %g]  pitch [%g, %g]" % (p["yaw_min"], p["yaw_max"], p["pitch_min"], p["pitch_max"]))
        for li, lod in enumerate(p["lods"]):
            mats = ", ".join(x["name"] for x in lod["materials"])
            print("   lod %d  dist %-8g  %5d verts  %5d faces  materials: %s" % (li, lod["distance"] or 0, len(lod["vertices"]), len(lod["faces"]), mats))
        if p["nodes"]:
            leaves = sum(1 for n in p["nodes"] if n["faces"])
            print("   nodes: %d (%d leaves with face lists)" % (len(p["nodes"]), leaves))
        for a in p["attachments"]:
            extra = ""
            if a["type"] == 0:
                extra = "  presets %s  mask %s" % (a["p13"], a["p19"])
            elif a["type"] == 4:
                extra = "  colour %s  size %s  blink %s  range %s  intensity %s" % (
                    a["p13"][0], fv(a["size"], 0), a["blink"], a["range"], a["intensity"])
            print("   attach type %s %-24s at %s%s" % (a["type"], ATTACH_TYPES.get(a["type"], "?"), fv(a["position"]), extra))
        for c in p["clips"]:
            print("   clip %-20r length %-6s mode %s  keys %d  events %d"
                  % (c["name"], c["length"], CLIP_MODES.get(c["mode"], c["mode"]), len(c["keys"]), len(c["events"])))
            for k in c["keys"][: args.keys]:
                print("      t=%-5s rot %s  trans %s" % (k["time"], fv(k["rotation"], 3), fv(k["translation"], 2)))
        for g in p["groups"]:
            print("   group class %s: %d entries%s" % (g["class"], len(g["entries"]),
                  "  e.g. face %s at %s" % (g["entries"][0]["face"], fv(g["entries"][0]["position"])) if g["entries"] else ""))
        for q in p["trigger_polys"]:
            print("   trigger polygon vertices %s" % (q["v"],))
    if m.tail:
        print("tail: %d record(s), first direction %s" % (len(m.tail), fv(m.tail[0]["direction"], 3)))


def cmd_dump(args):
    m = read_model(args.file)
    want = int(args.tag, 0)
    shown = 0
    for k, tag, esz, cnt, off in m.chunks:
        if tag != want:
            continue
        print("chunk %d  tag %02x (%s)  record %d B  count %d" % (k, tag, TAGS.get(tag, ("?",))[0], esz, cnt))
        for j in range(min(cnt, args.count)):
            b = m.img[off + j * esz: off + (j + 1) * esz]
            cols = " ".join("%02x=%s" % (i, cell(b, i)) for i in range(0, len(b) - len(b) % 4, 4))
            print("  [%3d] %s" % (j, cols))
            dec = DECODERS.get(tag)
            if dec and args.decode:
                print("        -> %s" % dec(b))
        shown += 1
        if shown >= args.chunks:
            break
    if not shown:
        print("no chunk with tag %#x" % want)


def cmd_obj(args):
    m = read_model(args.file)
    lines = ["# %s  exported by shp_parse.py (LOD %d)" % (m.name, args.lod),
             "# coordinates are the model's own units; UVs are written as stored (u, v)"]
    vbase = 1
    vt_base = 0
    written = 0
    for pi, p in enumerate(m.parts):
        if args.part is not None and pi != args.part:
            continue
        if args.lod >= len(p["lods"]):
            continue
        lod = p["lods"][args.lod]
        if not lod["vertices"]:
            continue
        offset = (0.0, 0.0, 0.0)
        if args.assemble:
            # sum part positions up the parent chain (rotation is not applied)
            ox, oy, oz, cur, hops = 0.0, 0.0, 0.0, pi, 0
            while cur is not None and 0 <= cur < len(m.parts) and hops < 64:
                pos = m.parts[cur]["position"] or (0, 0, 0)
                ox, oy, oz = ox + pos[0], oy + pos[1], oz + pos[2]
                parent = m.parts[cur]["parent"]
                cur = parent if parent not in (None, -1) else None
                hops += 1
            offset = (ox, oy, oz)
        lines.append("o part%d_%s" % (pi, "".join(ch if ch.isalnum() else "_" for ch in p["name"])))
        for v in lod["vertices"]:
            x, y, z = v["position"]
            lines.append("v %.6g %.6g %.6g" % (x + offset[0], y + offset[1], z + offset[2]))
        for v in lod["vertices"]:
            lines.append("vn %.6g %.6g %.6g" % v["normal"])
        # per-corner UVs: one vt per distinct (u, v) pair in this LOD
        vt_index = {}
        vts = []
        for f in lod["faces"]:
            for u, vv in zip(f["u"], f["vt"]):
                key = (round(u or 0.0, 6), round(vv or 0.0, 6))
                if key not in vt_index:
                    vt_index[key] = len(vts) + 1
                    vts.append(key)
        for u, vv in vts:
            lines.append("vt %.6g %.6g" % (u, vv))
        last_mat = None
        nv = len(lod["vertices"])
        for f in lod["faces"]:
            if f["mode"] == 1 and not args.wire:
                continue                                   # type-1 = wire/outline primitives
            mi = f["material"]
            mat = lod["materials"][mi]["name"] if mi is not None and mi < len(lod["materials"]) else "material%s" % mi
            if mat != last_mat:
                lines.append("usemtl %s" % (mat or "unnamed"))
                last_mat = mat
            if any(v is None or v >= nv for v in f["v"]):
                continue
            corners = []
            for k in range(3):
                key = (round(f["u"][k] or 0.0, 6), round(f["vt"][k] or 0.0, 6))
                corners.append("%d/%d/%d" % (vbase + f["v"][k], vt_base + vt_index[key], vbase + f["v"][k]))
            lines.append("f " + " ".join(corners))
            written += 1
        vbase += nv
        vt_base += len(vts)
    with open(args.out, "w") as fh:
        fh.write("\n".join(lines) + "\n")
    if not getattr(args, "quiet", False):
        print("wrote %s: %d triangles from %d part(s), LOD %d" % (args.out, written, len(m.parts), args.lod))


def cmd_sweep(args):
    files = sorted(glob.glob(os.path.join(args.dir, "*.shp")) + glob.glob(os.path.join(args.dir, "*.SHP")))
    files = sorted(set(files), key=str.lower)
    if not files:
        sys.exit("no .shp files in %s" % args.dir)
    sizes = collections.defaultdict(collections.Counter)
    totals = collections.Counter()
    ok = 0
    for path in files:
        name = os.path.basename(path)
        try:
            m = read_model(path)
            problems = m.validate()
        except SHPError as e:
            print("  FAIL %-28s %s" % (name, e))
            continue
        except Exception as e:                           # never a traceback on bad input
            print("  FAIL %-28s unexpected: %s" % (name, e))
            continue
        for _, tag, esz, cnt, _ in m.chunks:
            sizes[tag][esz] += 1
            totals[tag] += cnt
        if problems:
            print("  WARN %-28s %s" % (name, "; ".join(problems[:3])))
        else:
            ok += 1
        if args.verbose:
            print("  ok   %-28s parts %2d  verts %6d  faces %6d" % (
                name, len(m.parts), sum(len(l["vertices"]) for p in m.parts for l in p["lods"]),
                sum(len(l["faces"]) for p in m.parts for l in p["lods"])))
    print("\n%d/%d decoded and structurally valid" % (ok, len(files)))
    print("record-size versions per tag (size: chunks) and total records:")
    for tag in sorted(sizes):
        print("  tag %02x %-16s %-40s records %d" % (tag, TAGS.get(tag, ("?",))[0],
              ", ".join("%d: %d" % kv for kv in sorted(sizes[tag].items())), totals[tag]))


# --------------------------------------------------------------------------- #
#  Self-test: synthetic model, literal-only RefPack packing, round trip         #
# --------------------------------------------------------------------------- #
def refpack_pack_literal(data):
    """Wrap bytes in a RefPack stream using literal runs only (valid, uncompressed)."""
    out = bytearray(b"\x10\xFB" + struct.pack(">I", len(data))[1:])
    i = 0
    while len(data) - i >= 4:
        n = min(112, (len(data) - i) // 4 * 4)
        out.append(0xE0 | (n // 4 - 1))
        out += data[i:i + n]
        i += n
    rest = data[i:]
    out.append(0xFC | len(rest))
    out += rest
    return bytes(out)


def chunk(tag, size, records):
    body = b"".join(r.ljust(size, b"\0")[:size] for r in records)
    return struct.pack("<HHH", tag, size, len(records)) + body


def build_synthetic():
    hdr = struct.pack("<I", 107) + b"\0" * 16 + struct.pack("<I", 0)
    part = bytearray(312)
    part[0:9] = b"Test part"
    struct.pack_into("<I", part, 0x40, 2)
    struct.pack_into("<3f", part, 0x44, 1.0, 2.0, 3.0)
    struct.pack_into("<3f", part, 0x50, -1.0, -1.0, 0.0)
    struct.pack_into("<3f", part, 0x5C, 1.0, 1.0, 0.0)
    struct.pack_into("<i", part, 0x94, -1)
    struct.pack_into("<9f", part, 0xA4, 1, 0, 0, 0, 1, 0, 0, 0, 1)
    struct.pack_into("<I", part, 0xF0, 0x30)
    verts = [struct.pack("<3f3fIi", x, y, 0.0, 0.0, 0.0, 1.0, 1, 0) for x, y in ((-1, -1), (1, -1), (0, 1))]
    face = struct.pack("<3I", 0, 0x16, 0) + struct.pack("<3I", 0, 1, 2) + struct.pack("<6f", 0, 1, 0.5, 0, 0, 1)
    face += struct.pack("<3f", 0, 0, 1) + struct.pack("<IfIII", 1, 0.0, 0, 0, 0)
    att = bytearray(168)
    struct.pack_into("<I3f", att, 0, 0, 5.0, 6.0, 7.0)
    struct.pack_into("<9f", att, 0x10, 1, 0, 0, 0, 1, 0, 0, 0, 1)
    struct.pack_into("<4I", att, 0x34, 0, 5, 8, 6)
    clip = struct.pack("<HHH", 100, 0, 1) + b"fire".ljust(18, b"\0")
    keys = [struct.pack("<i6f", 0, 0, 0, 0, 0, 0, 0), struct.pack("<i6f", 100, 0, 1.5708, 0, 0, 0, 0)]
    img = (chunk(0, 24, [hdr]) + chunk(1, 312, [bytes(part)]) + chunk(2, 4, [struct.pack("<f", 0)])
           + chunk(7, 72, []) + chunk(9, 168, [bytes(att)]) + chunk(0xA, 24, [clip]) + chunk(0xD, 4, [])
           + chunk(0xF, 16, []) + chunk(4, 32, verts) + chunk(3, 80, [face])
           + chunk(6, 64, [b"TESTMAT"]) + chunk(0xB, 28, keys) + chunk(0xC, 12, []) + chunk(0x10, 76, [])
           + struct.pack("<HHH", 0xFFFF, 0, 0))
    return refpack_pack_literal(img)


def selftest():
    if refpack_decompress is None:
        print("shp_parse self-test: SKIPPED (dte_parse.py not importable)")
        return 0
    raw = build_synthetic()
    m = Model(raw, "synthetic")
    assert m.header["magic"] == 107 and m.header_size == 24, m.header
    assert len(m.parts) == 1, len(m.parts)
    p = m.parts[0]
    assert p["name"] == "Test part" and p["type"] == 2 and p["parent"] == -1, p
    assert p["position"] == (1.0, 2.0, 3.0) and p["flags"] == 0x30
    assert len(p["lods"]) == 1 and len(p["lods"][0]["vertices"]) == 3 and len(p["lods"][0]["faces"]) == 1
    f = p["lods"][0]["faces"][0]
    assert f["v"] == (0, 1, 2) and f["mode"] == 6 and f["submode"] == 1 and f["poly_kind"] == 0, f
    assert abs(f["u"][1] - 1.0) < 1e-6 and abs(f["vt"][2] - 1.0) < 1e-6
    assert p["lods"][0]["materials"][0]["name"] == "TESTMAT"
    assert len(p["attachments"]) == 1 and p["attachments"][0]["type"] == 0
    assert p["attachments"][0]["position"] == (5.0, 6.0, 7.0) and p["attachments"][0]["p13"] == (0, 5, 8, 6)
    assert len(p["clips"]) == 1 and p["clips"][0]["name"] == "fire" and p["clips"][0]["length"] == 100
    assert p["clips"][0]["mode"] == 1 and len(p["clips"][0]["keys"]) == 2
    assert abs(p["clips"][0]["keys"][1]["rotation"][1] - 1.5708) < 1e-4
    assert p["nodes"] == [] and p["groups"] == [] and p["trigger_polys"] == [] and m.tail == []
    assert m.validate() == [], m.validate()
    # malformed inputs must raise SHPError, never crash
    for bad in (b"", b"\x00\x01\x02", raw[:20], raw[:-3]):
        try:
            Model(bad, "bad")
        except SHPError:
            pass
        else:
            raise AssertionError("malformed input accepted: %r" % bad[:8])
    # a stream whose image lacks the terminator
    truncated_img = refpack_pack_literal(m.img[:-6])
    try:
        Model(truncated_img, "no-terminator")
    except SHPError:
        pass
    else:
        raise AssertionError("missing terminator accepted")
    # OBJ export round trip through a temp dir
    import tempfile
    tmp = tempfile.mkdtemp(prefix="shp_selftest_")
    try:
        shp = os.path.join(tmp, "synthetic.shp")
        with open(shp, "wb") as fh:
            fh.write(raw)
        out = os.path.join(tmp, "synthetic.obj")
        ns = argparse.Namespace(file=shp, out=out, lod=0, part=None, assemble=True, wire=False, quiet=True)
        cmd_obj(ns)
        text = open(out).read()
        # vertex (-1,-1,0) + part position (1,2,3) -> (0,1,3) when --assemble is on
        assert "usemtl TESTMAT" in text and text.count("\nf ") == 1 and "\nv 0 1 3\n" in text, text
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)
    print("shp_parse self-test: OK (synthetic model round-trip, malformed-input handling, OBJ export)")
    return 0


# --------------------------------------------------------------------------- #
def main(argv=None):
    ap = argparse.ArgumentParser(description="Starlancer .SHP model decoder (static, read-only).")
    ap.add_argument("--selftest", action="store_true", help="run the built-in synthetic round-trip test")
    sub = ap.add_subparsers(dest="cmd")
    p = sub.add_parser("info", help="chunk walk"); p.add_argument("file"); p.set_defaults(fn=cmd_info)
    p = sub.add_parser("tree", help="decoded structure"); p.add_argument("file")
    p.add_argument("--keys", type=int, default=4, help="keyframes to show per clip"); p.set_defaults(fn=cmd_tree)
    p = sub.add_parser("dump", help="typed record dump of one tag"); p.add_argument("file")
    p.add_argument("--tag", required=True, help="chunk tag, e.g. 9 or 0x9")
    p.add_argument("-n", "--count", type=int, default=16, help="records per chunk")
    p.add_argument("--chunks", type=int, default=3, help="how many chunks with that tag")
    p.add_argument("--decode", action="store_true", help="also print the named-field decode")
    p.set_defaults(fn=cmd_dump)
    p = sub.add_parser("obj", help="export one LOD as Wavefront OBJ"); p.add_argument("file")
    p.add_argument("-o", "--out", required=True); p.add_argument("--lod", type=int, default=0)
    p.add_argument("--part", type=int, default=None, help="only this part index")
    p.add_argument("--assemble", action="store_true", help="offset parts by their (parent-chain) positions")
    p.add_argument("--wire", action="store_true", help="include type-1 wire/outline primitives")
    p.set_defaults(fn=cmd_obj)
    p = sub.add_parser("sweep", help="decode + validate every .shp in a folder"); p.add_argument("dir")
    p.add_argument("-v", "--verbose", action="store_true"); p.set_defaults(fn=cmd_sweep)
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if not args.cmd:
        ap.print_help()
        return 2
    try:
        args.fn(args)
    except SHPError as e:
        print("error: %s" % e, file=sys.stderr)
        return 1
    except (OSError, IOError) as e:
        print("error: %s" % e, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
