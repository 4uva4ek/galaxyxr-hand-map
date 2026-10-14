"""ANTR hand map: write an exported edit JSON into the kEditedBind table of the overport-galaxyxr adapter.

Usage: python -I ANTR-update-edited-table.py EXPORT_JSON HAND_TRACKING_INC
  EXPORT_JSON        the JSON produced by the "Собрать JSON правок" (export) button of the hand map
  HAND_TRACKING_INC  path to native/galaxyxr/hand_tracking.inc in the overport-galaxyxr checkout

Only the 26 rows between "static const float kEditedBind[...] = {" and "};" are replaced; the script is idempotent.
The table is the left hand in the OpenXR wrist frame (metres, quaternion xyzw); the adapter mirrors X for the
right hand and rebuilds every orientation from the positions and the +Y roll, so q_xyzw only has to carry the roll.
Export the LEFT hand: the table is defined for the left hand. Rebuild the adapter and the CLI afterwards and convert
the game with --hand-bind=edited.
"""
import json
import os
import re
import sys

XR_NAMES = ["palm", "wrist", "th_meta", "th_prox", "th_dist", "th_tip", "ix_meta", "ix_prox", "ix_inter", "ix_dist", "ix_tip",
            "md_meta", "md_prox", "md_inter", "md_dist", "md_tip", "rg_meta", "rg_prox", "rg_inter", "rg_dist", "rg_tip",
            "lt_meta", "lt_prox", "lt_inter", "lt_dist", "lt_tip"]
TABLE = re.compile(r"(static const float kEditedBind\[XR_HAND_JOINT_COUNT_EXT\]\[7\] = \{\n)(.*?)(\n\};)", re.S)


def main():
    if len(sys.argv) != 3:
        print(__doc__); sys.exit(2)
    export_path, inc_path = sys.argv[1], sys.argv[2]
    ed = json.load(open(export_path, encoding="utf-8"))
    joints = ed["joints"]
    if len(joints) != 26 or [j["name"] for j in joints] != XR_NAMES:
        sys.exit("export must contain the 26 OpenXR joints in order: " + ", ".join(XR_NAMES))
    if ed.get("side", "left") != "left":
        sys.exit("export the left hand: kEditedBind is a left-hand table and the adapter mirrors it for the right hand")
    rows = []
    for j in joints:
        p = [v / 1000.0 for v in j["p_mm"]]
        q = j["q_xyzw"]; n = sum(c * c for c in q) ** 0.5
        if n < 1e-6: sys.exit(f"{j['name']}: zero quaternion")
        q = [c / n for c in q]
        rows.append("    {%s, %s},  // %s" % (", ".join("%.5ff" % v for v in p), ", ".join("%.5ff" % v for v in q), j["name"]))
    text = open(inc_path, encoding="utf-8").read()
    m = TABLE.search(text)
    if not m: sys.exit("kEditedBind table not found in " + inc_path)
    new = text[:m.start(2)] + "\n".join(rows) + text[m.end(2):]
    if new == text:
        print("table already up to date:", len(rows), "rows"); return
    open(inc_path, "w", encoding="utf-8", newline="\n").write(new)
    print("table updated:", len(rows), "rows in", os.path.abspath(inc_path))


if __name__ == "__main__":
    main()
