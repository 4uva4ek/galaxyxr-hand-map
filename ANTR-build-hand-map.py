"""ANTR hand map: inline the extracted joint data into the page template.

Usage: python -I ANTR-build-hand-map.py [data.json] [out.html]
Defaults: ANTR-hand-map-data.json -> ANTR-hand-map.html next to this script.
Regenerate the data with ANTR-extract-hand-map.py (it reads a GXR_HAND_DIAGNOSTICS logcat extract and optionally OVRSkeletonData.cs).
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
data_path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "ANTR-hand-map-data.json")
out_path = sys.argv[2] if len(sys.argv) > 2 else os.path.join(HERE, "ANTR-hand-map.html")
template = open(os.path.join(HERE, "ANTR-hand-map.template.html"), encoding="utf-8").read()
data = open(data_path, encoding="utf-8").read().replace("</", "<\\/")
assert "__DATA__" in template
open(out_path, "w", encoding="utf-8", newline="\n").write(template.replace("__DATA__", data))
print("wrote", out_path, os.path.getsize(out_path), "bytes")
