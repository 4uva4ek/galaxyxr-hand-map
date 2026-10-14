"""GXR hand map: collect every hand-joint layer captured for a converted Quest game on Galaxy XR into one JSON.

Usage: python -I GXR-extract-hand-map.py HAND_LINES [--meta OVRSkeletonData.cs] [--out data.json]
  HAND_LINES  logcat extract with the "OverportGXR: HAND" lines of a GXR_HAND_DIAGNOSTICS adapter build
  --meta      OVRSkeletonData.cs from the Oculus Integration (Quest reference rest pose); omit to skip the meta layer
  --out       output path (default: GXR-hand-map-data.json next to this script)

Layers (per side, 0 = left, 1 = right):
  live     - XR_EXT_hand_tracking joints logged by the diagnostics adapter, world space,
             raw orientation plus the orientation after alignHandFrames (handframes=meta).
  bind     - the rebuilt XR_FB_hand_tracking_mesh bind pose the adapter hands to OVRPlugin (OVR root frame).
  ovrp     - ovrp_GetSkeleton2 bone rest pose OVRPlugin derived from it (parent-relative -> root-relative).
  meta     - Oculus Integration OVRSkeletonData rest pose (Quest reference), root-relative.
All OVR-frame layers are also stored converted into the OpenXR wrist frame (rotate by conj(C_hand)) so they overlay
the live joints (wrist at the origin, -Z toward the fingers, +Y back of the hand).
Read-only on its inputs.
"""
import argparse
import json
import math
import os
import re
import struct

HERE = os.path.dirname(os.path.abspath(__file__))

VEC = r"\(\s*(-?[\d.]+)\s+(-?[\d.]+)\s+(-?[\d.]+)\s*\)"
QUAT = r"\(\s*(-?[\d.]+)\s+(-?[\d.]+)\s+(-?[\d.]+)\s+(-?[\d.]+)\s*\)"
LOCATE = re.compile(r"HAND locate tracker=(0x[0-9a-f]+) side=(-?\d+) result=(-?\d+) active=(\d)")
JOINT = re.compile(r"HAND joint tracker=(0x[0-9a-f]+) j=(\d+) flags=([0-9a-f]+) r=([\d.]+) p=" + VEC + r" q=" + QUAT)
SKELRAW = re.compile(r"HAND ovrp skelraw side=(\d+) off=(\d+) ([0-9a-f]+)")
MESH = re.compile(r"HAND mesh tracker=(0x[0-9a-f]+) result=(-?\d+) fixed=(\d)")
BIND = re.compile(r"HAND bind j=(\d+) parent=(-?\d+) r=([\d.]+) p=" + VEC + r" q=" + QUAT)
TIME = re.compile(r"^(\d\d-\d\d \d\d:\d\d:\d\d\.\d+)")

XR_NAMES = ["palm", "wrist", "th_meta", "th_prox", "th_dist", "th_tip", "ix_meta", "ix_prox", "ix_inter", "ix_dist", "ix_tip",
            "md_meta", "md_prox", "md_inter", "md_dist", "md_tip", "rg_meta", "rg_prox", "rg_inter", "rg_dist", "rg_tip",
            "lt_meta", "lt_prox", "lt_inter", "lt_dist", "lt_tip"]
XR_PARENT = [1, -1, 1, 2, 3, 4, 1, 6, 7, 8, 9, 1, 11, 12, 13, 14, 1, 16, 17, 18, 19, 1, 21, 22, 23, 24]
OVR_NAMES = ["WristRoot", "ForearmStub", "Thumb0", "Thumb1", "Thumb2", "Thumb3", "Index1", "Index2", "Index3", "Middle1", "Middle2", "Middle3",
             "Ring1", "Ring2", "Ring3", "Pinky0", "Pinky1", "Pinky2", "Pinky3", "ThumbTip", "IndexTip", "MiddleTip", "RingTip", "PinkyTip"]
# OVR bone index -> XR joint it corresponds to (Meta has no index/middle/ring metacarpal bones).
OVR_TO_XR = {0: 1, 2: 2, 3: 2, 4: 3, 5: 4, 19: 5, 6: 7, 7: 8, 8: 9, 20: 10, 9: 12, 10: 13, 11: 14, 21: 15, 12: 17, 13: 18, 14: 19, 22: 20,
             15: 21, 16: 22, 17: 23, 18: 24, 23: 25}
C_HAND = {0: (0.70710677, 0.0, -0.70710677, 0.0), 1: (0.0, 0.70710677, 0.0, 0.70710677)}
LITTLE_META_ROLL = math.radians(24.0)


def qmul(a, b):
    ax, ay, az, aw = a; bx, by, bz, bw = b
    return (aw * bx + ax * bw + ay * bz - az * by, aw * by - ax * bz + ay * bw + az * bx,
            aw * bz + ax * by - ay * bx + az * bw, aw * bw - ax * bx - ay * by - az * bz)
def qconj(q): return (-q[0], -q[1], -q[2], q[3])
def rot(q, v): return qmul(qmul(q, (v[0], v[1], v[2], 0.0)), qconj(q))[:3]
def add(a, b): return tuple(x + y for x, y in zip(a, b))
def sub(a, b): return tuple(x - y for x, y in zip(a, b))
def scale(a, s): return tuple(x * s for x in a)
def dot(a, b): return sum(x * y for x, y in zip(a, b))
def cross(a, b): return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])
def length(a): return math.sqrt(dot(a, a))
def normalize(a):
    l = length(a); return scale(a, 1.0 / l) if l > 1e-6 else (0.0, 0.0, 1.0)
def r4(v): return [round(x, 5) for x in v]


def from_axes(x, y, z):
    m00, m01, m02, m10, m11, m12, m20, m21, m22 = x[0], y[0], z[0], x[1], y[1], z[1], x[2], y[2], z[2]
    t = m00 + m11 + m22
    if t > 0:
        s = math.sqrt(t + 1.0) * 2; return ((m21 - m12) / s, (m02 - m20) / s, (m10 - m01) / s, 0.25 * s)
    if m00 > m11 and m00 > m22:
        s = math.sqrt(1.0 + m00 - m11 - m22) * 2; return (0.25 * s, (m01 + m10) / s, (m02 + m20) / s, (m21 - m12) / s)
    if m11 > m22:
        s = math.sqrt(1.0 + m11 - m00 - m22) * 2; return ((m01 + m10) / s, 0.25 * s, (m12 + m21) / s, (m02 - m20) / s)
    s = math.sqrt(1.0 + m22 - m00 - m11) * 2; return ((m02 + m20) / s, (m12 + m21) / s, 0.25 * s, (m10 - m01) / s)


def bone_frame(joint, child, up):
    z = normalize(sub(joint, child))
    y = normalize(sub(up, scale(z, dot(up, z))))
    return from_axes(cross(y, z), y, z)


def align_hand_frames(joints):
    """Port of alignHandFrames (hand_tracking.inc): returns {j: new orientation} for the wrist and little metacarpal."""
    out = {}
    wp, wq = joints[1]; pq = joints[0][1]
    z = rot(wq, (0, 0, 1)); palm_up = rot(pq, (0, 1, 0))
    y = sub(palm_up, scale(z, dot(palm_up, z)))
    if length(y) < 0.2: return out
    y = normalize(y); wq2 = from_axes(cross(y, z), y, z); out[1] = wq2
    mp = joints[21][0]; prox = joints[22][0]
    if length(sub(prox, mp)) < 0.01: return out
    ulnar = -1.0 if dot(sub(prox, wp), rot(wq2, (1, 0, 0))) < 0 else 1.0
    up = rot(wq2, (ulnar * math.sin(LITTLE_META_ROLL), math.cos(LITTLE_META_ROLL), 0))
    out[21] = bone_frame(mp, prox, up)
    return out


def accumulate(bones):
    """bones: list of (parent, p, q) parent-relative -> list of (p, q) root-relative."""
    world = []
    for parent, p, q in bones:
        if parent < 0 or parent >= len(world): world.append((p, q))
        else:
            pp, pq = world[parent]; world.append((add(pp, rot(pq, p)), qmul(pq, q)))
    return world


def to_xr_frame(side, p, q):
    c = qconj(C_HAND[side])
    return rot(c, p), qmul(c, q)


def parse_diag(path):
    text = open(path, encoding="utf-8", errors="replace").read()
    samples, current, raw, bind, mesh_tracker, side_of = [], {}, {}, {}, None, {}
    for line in text.splitlines():
        m = LOCATE.search(line)
        if m:
            tr, side = m.group(1), int(m.group(2)); side_of[tr] = side
            t = TIME.match(line)
            s = {"side": side, "time": t.group(1) if t else "", "joints": {}}
            current[tr] = s; samples.append(s); continue
        m = JOINT.search(line)
        if m and m.group(1) in current:
            g = [float(x) for x in m.groups()[3:]]
            current[m.group(1)]["joints"][int(m.group(2))] = (g[0], tuple(g[1:4]), tuple(g[4:8])); continue
        m = SKELRAW.search(line)
        if m: raw.setdefault(int(m.group(1)), {})[int(m.group(2))] = bytes.fromhex(m.group(3)); continue
        m = MESH.search(line)
        if m: mesh_tracker = m.group(1) if m.group(3) == "1" else None; continue
        m = BIND.search(line)
        if m and mesh_tracker:
            g = [float(x) for x in m.groups()[2:]]
            bind.setdefault(mesh_tracker, {})[int(m.group(1))] = (int(m.group(2)), g[0], tuple(g[1:4]), tuple(g[4:8]))
    skeleton = {}
    for side, chunks in raw.items():
        blob = b"".join(chunks[o] for o in sorted(chunks))
        stype, nbones, ncaps = struct.unpack_from("<iII", blob, 0)
        bones = []
        for i in range(min(nbones, 25)):
            off = 12 + 36 * i
            if off + 36 > len(blob): break
            bid, parent, pad, qx, qy, qz, qw, px, py, pz = struct.unpack_from("<ihh7f", blob, off)
            bones.append((bid, parent, (px, py, pz), (qx, qy, qz, qw)))
        skeleton[side] = bones
    return samples, skeleton, {side_of.get(tr, -1): b for tr, b in bind.items()}


def parse_meta(path):
    text = open(path, encoding="utf-8", errors="replace").read()
    bone_re = re.compile(r"Id=OVRPlugin\.BoneId\.(\w+), ParentBoneIndex=(-?\d+), Pose=new OVRPlugin\.Posef\(\) \{ Position=new OVRPlugin\.Vector3f\(\) \{x=([^f]+)f,y=([^f]+)f,z=([^f]+)f\}, Orientation=new OVRPlugin\.Quatf\(\)\{x=([^f]+)f,y=([^f]+)f,z=([^f]+)f,w=([^f]+)f\}")
    result = {}
    for side, key in ((0, "LeftSkeleton"), (1, "RightSkeleton")):
        start = text.index(key); end = text.index("BoneCapsules = new", start)
        bones = []
        for m in bone_re.finditer(text, start, end):
            g = [float(x) for x in m.groups()[2:]]
            bones.append((m.group(1), int(m.group(2)), tuple(g[0:3]), tuple(g[3:7])))
        result[side] = bones
    return result


def main():
    ap = argparse.ArgumentParser(description="Build the GXR hand map data JSON from a HAND logcat extract.")
    ap.add_argument("hand_lines", help="logcat extract with the OverportGXR: HAND lines")
    ap.add_argument("--meta", help="OVRSkeletonData.cs from the Oculus Integration (optional)")
    ap.add_argument("--out", default=os.path.join(HERE, "GXR-hand-map-data.json"), help="output JSON path")
    args = ap.parse_args()
    samples, skeleton, bind = parse_diag(args.hand_lines)
    meta = parse_meta(args.meta) if args.meta else {}
    out = {"source": {"diag": os.path.basename(args.hand_lines), "meta": os.path.basename(args.meta) if args.meta else None},
           "xrNames": XR_NAMES, "xrParents": XR_PARENT, "ovrNames": OVR_NAMES, "ovrToXr": {str(k): v for k, v in OVR_TO_XR.items()},
           "sides": {}}
    for side in (0, 1):
        live = []
        for s in samples:
            if s["side"] != side or len(s["joints"]) != 26: continue
            j = {k: (p, q) for k, (r, p, q) in s["joints"].items()}
            aligned = align_hand_frames(j)
            p = {k: j[k][0] for k in j}
            def curl(a, b, c):
                return math.degrees(math.acos(max(-1.0, min(1.0, dot(normalize(sub(p[b], p[a])), normalize(sub(p[c], p[b])))))))
            live.append({
                "time": s["time"], "indexCurl": round(curl(7, 8, 10), 1), "middleCurl": round(curl(12, 13, 15), 1),
                "joints": [{"r": round(s["joints"][k][0], 4), "p": r4(j[k][0]), "q": r4(j[k][1]), "qAligned": r4(aligned.get(k, j[k][1]))} for k in range(26)]})
        entry = {"live": live}
        if side in bind:
            b = bind[side]
            entry["bind"] = [{"parent": b[k][0], "r": round(b[k][1], 4), "pOvr": r4(b[k][2]), "qOvr": r4(b[k][3]),
                              "p": r4(to_xr_frame(side, b[k][2], b[k][3])[0]), "q": r4(to_xr_frame(side, b[k][2], b[k][3])[1])} for k in range(26)]
        if side in skeleton:
            bones = skeleton[side]
            world = accumulate([(parent, p, q) for bid, parent, p, q in bones])
            entry["ovrp"] = [{"id": bid, "name": OVR_NAMES[bid] if 0 <= bid < 24 else str(bid), "parent": parent, "xr": OVR_TO_XR.get(i),
                              "pLocal": r4(p), "qLocal": r4(q), "pOvr": r4(world[i][0]), "qOvr": r4(world[i][1]),
                              "p": r4(to_xr_frame(side, world[i][0], world[i][1])[0]), "q": r4(to_xr_frame(side, world[i][0], world[i][1])[1])}
                             for i, (bid, parent, p, q) in enumerate(bones)]
        if side in meta:
            bones = meta[side]
            world = accumulate([(parent, p, q) for name, parent, p, q in bones])
            entry["meta"] = [{"name": name.replace("Hand_", ""), "parent": parent, "xr": OVR_TO_XR.get(i),
                              "pLocal": r4(p), "qLocal": r4(q), "pOvr": r4(world[i][0]), "qOvr": r4(world[i][1]),
                              "p": r4(to_xr_frame(side, world[i][0], world[i][1])[0]), "q": r4(to_xr_frame(side, world[i][0], world[i][1])[1])}
                             for i, (name, parent, p, q) in enumerate(bones)]
        out["sides"][str(side)] = entry
        print(f"side {side}: live samples={len(live)} bind={'yes' if 'bind' in entry else 'no'} ovrp bones={len(entry.get('ovrp', []))} meta bones={len(entry.get('meta', []))}")
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(out, f, separators=(",", ":"))
    print("wrote", args.out, os.path.getsize(args.out), "bytes")


if __name__ == "__main__":
    main()
