# GXR hand map

Interactive map of the hand joints that a converted Quest game sees on **Samsung Galaxy XR**.
It overlays, in one 3D view, the live `XR_EXT_hand_tracking` joints of the Galaxy XR runtime,
the bind pose that the [overport-galaxyxr](https://github.com/4uva4ek/overport-galaxyxr) adapter
hands to OVRPlugin, the rest skeleton the game actually receives, and the Quest reference rest
pose. A draggable edit layer lets you tune a bind pose by hand and export it as the table the
adapter uses with `--hand-bind=edited`.

Single-file HTML, no build tools. Python 3 (standard library only) regenerates the data from a
logcat capture. Maintained by **4uva4ek**.

Русская версия: [docs/README.ru.md](docs/README.ru.md).

## Contents

| File | Purpose |
| --- | --- |
| `GXR-hand-map.html` | The map with the bundled data. Open it in a browser; nothing else is needed. |
| `GXR-hand-map.template.html` | The page without data; `__DATA__` is replaced by the JSON. |
| `GXR-hand-map-data.json` | Joint layers extracted from `samples/hand-diag5-lines.txt` and `OVRSkeletonData.cs`. |
| `GXR-extract-hand-map.py` | Builds the data JSON from a `HAND` logcat extract (and optionally the Meta rest pose). |
| `GXR-build-hand-map.py` | Inlines the JSON into the template. |
| `GXR-update-edited-table.py` | Writes an exported edit JSON into `kEditedBind` in the adapter source. |
| `samples/hand-diag5-lines.txt` | Reference capture: Job Simulator 1.4.0.6515 on SM-I610 (I610UEU2AZF3), 2026-10-14. |
| `samples/hand-edits-left-reference.json` | Reference export: the current built-in `handbind=edited` table of the adapter. |
| `samples/hand-edits-left-20261014.json` | Earlier export, kept for comparison. |

## 1. Where the logs come from

The data is produced by the **diagnostics build** of the overport-galaxyxr adapter. The release
adapter does not log joints, so a game converted with a release CLI gives nothing to extract.

### 1.1 Build the adapter with hand diagnostics

In a checkout of overport-galaxyxr (Linux or WSL, Android NDK r29 in `ANDROID_NDK_HOME`):

```bash
GXR_HAND_DIAGNOSTICS=1 bash native/galaxyxr/build.sh
./gradlew :overportcli:shadowJar
```

The first command compiles `native/galaxyxr/policy.cpp` with `-DGXR_HAND_DIAGNOSTICS` and
writes `libopenxr_loader_generic.bin` into the CLI resources; the second packages the CLI jar
(`overportcli/build/libs/`). The diagnostics build adds, besides the normal adapter behaviour:

- `HAND create` / `HAND locate` / `HAND joint`: every `xrLocateHandJointsEXT` result, rate
  limited to one sample per tracker every 2 seconds, with all 26 joints (position, orientation,
  radius, flags) in world space.
- `HAND mesh` / `HAND bind`: the `XR_FB_hand_tracking_mesh` description after the adapter
  rebuilt it (26 joints with parents, radii and bind poses in the OVR root frame).
- `HAND ovrp skeleton` / `skelraw` / `skelbone`: the `ovrp_GetSkeleton2` rest skeleton read back
  from OVRPlugin 1.88, exactly as the game receives it. The observer is read-only and only exists
  in the diagnostics build.

### 1.2 Convert and install the game

```bash
java -jar overport-galaxyxr-<version>-cli.jar patch --input=game.apk --target=galaxyxr --hands=on
adb install -r <output>.apk
```

`--hands=on` makes the converted game request the Android XR `HAND_TRACKING` permission at
launch; without the permission the runtime never returns active joints. Other hand options that
influence the capture: `--hand-mesh=fix|runtime`, `--hand-frames=meta|runtime`,
`--hand-bind=rebuild|edited`. Record which ones you used; the `bind` and `ovrp` layers show
their effect. The CLI writes the chosen options into
`lib/arm64-v8a/liboverport.galaxyxr.config.so` inside the APK (`handmesh=`, `handframes=`,
`handbind=` lines), which is how the adapter reads them.

This is an ordinary app install. Nothing on the headset outside the converted game is changed.

### 1.3 Capture the logcat

Stream the adapter tag to a file for the whole session, so the ring buffer cannot overflow
(a full session is tens of megabytes of logcat):

```bash
adb logcat -c
adb logcat -v threadtime -s OverportGXR > overport-logcat.txt
```

Then, in the headset:

1. Launch the converted game and grant the hand-tracking permission when asked.
2. Keep both hands in view and tracked. The game asks for the hand mesh (`HAND mesh`, `HAND
   bind`) the first time hands become tracked; the OVRPlugin skeleton (`HAND ovrp`) is logged
   once per tracker right after that.
3. Hold the hands open with the fingers straight and spread for a few seconds. Live samples are
   logged every 2 seconds per hand; the map picks the sample with the straightest index and
   middle finger as its default, and the slider shows all of them.
4. Stop the capture with `Ctrl+C`.

Extract the `HAND` lines (the extractor ignores every other line, so you can also pass the full
logcat, it is just slower):

```bash
grep "OverportGXR: HAND" overport-logcat.txt > hand-lines.txt
```

PowerShell:

```powershell
Select-String -Path overport-logcat.txt -Pattern "OverportGXR: HAND" | ForEach-Object Line | Set-Content -Encoding utf8 hand-lines.txt
```

A usable extract contains, per hand: `HAND locate ... result=0 active=1` followed by 26
`HAND joint` lines, one `HAND mesh ... fixed=1` followed by 26 `HAND bind` lines, and
`HAND ovrp skelraw` lines. `samples/hand-diag5-lines.txt` is a complete example.

### 1.4 Quest reference rest pose (optional)

The `meta` layer comes from `OVRSkeletonData.cs` of the Oculus Integration for Unity
(`Assets/Oculus/Interaction/Runtime/Scripts/Input/OVRIntegration/OVRSkeletonData.cs` in any
Unity project that ships the Meta XR Interaction SDK). It is Meta code and is not included here;
pass your own copy with `--meta`. Without it the map simply has no `meta` layer. The bundled
`GXR-hand-map-data.json` already contains the derived rest pose.

## 2. Build the map

```bash
python -I GXR-extract-hand-map.py hand-lines.txt --meta OVRSkeletonData.cs
python -I GXR-build-hand-map.py
```

The first command writes `GXR-hand-map-data.json` next to the scripts (`--out` changes that)
and prints how many live samples and bones each side has. The second inlines it into
`GXR-hand-map.html`. Both scripts take explicit paths:
`GXR-build-hand-map.py [data.json] [out.html]`.

To rebuild the bundled map from the reference capture:

```bash
python -I GXR-extract-hand-map.py samples/hand-diag5-lines.txt --meta /path/to/OVRSkeletonData.cs
python -I GXR-build-hand-map.py
```

## 3. Using the map

Open `GXR-hand-map.html`. Everything is drawn in the **OpenXR wrist frame** of the selected
hand: the wrist at the origin, **−Z toward the fingers**, **+Y out of the back of the hand**,
+X toward the thumb on the left hand. The 1 cm grid lies in the plane of the current view.

**Hand**: the Left / Right buttons in the header switch sides. Layers, samples and edits are per
side.

**Layers** (checkboxes, colour coded):

- `live` (blue): the runtime joints of the selected sample, moved into the wrist frame.
- `bind` (red): the rebuilt `XR_FB_hand_tracking_mesh` bind pose the adapter returns; this is what
  OVRPlugin turns into the game skeleton.
- `ovrp` (violet): the `ovrp_GetSkeleton2` rest skeleton as the game receives it (24 OVR bones;
  OVR has no index/middle/ring metacarpal bones).
- `meta` (green): the Quest reference rest pose from `OVRSkeletonData.cs`.
- `edit` (amber): your editable copy of one layer.

**Live sample**: the slider steps through the logged samples of the selected hand, with the time
stamp and the index/middle curl angle. **Wrist frame** chooses the orientation used to place
everything: *aligned* is the wrist frame after the adapter's `alignHandFrames` (what
`--hand-frames=meta` produces), *raw* is the untouched Galaxy XR wrist orientation.

**View**: four preset cameras (back of hand, palm, thumb side, from the tips). Drag the empty
background to orbit, use the wheel to zoom. Checkboxes toggle joint names, bone lengths in
millimetres and the grid. **Joint axes** draws the local X (red), Y (green), Z (blue) axes of one
layer; the adapter convention is +Z along the bone toward the parent and +Y the roll.

Hovering a point prints its layer, name and coordinates in millimetres.

### 3.1 Editing a bind pose

1. Pick the **source** (`bind`, `live`, `ovrp` or `meta`) and press **Copy into edit**. The edit
   layer gets an independent copy with positions, orientations and parents.
2. Switch **Edit mode** on. Dragging an amber point moves it in the plane of the screen, so choose
   the view that shows the two axes you want to change. Axes switch to the edit layer
   automatically.
3. Click a point to open its editor: X/Y/Z inputs in millimetres (with the offset from the source),
   and rotation buttons around the joint's own axes in 1° and 5° steps: **X** flexes, **Y**
   spreads, **Z** rolls about the bone. With *rotate together with child joints* on, the whole
   subtree turns like a skeleton; off, only this joint's orientation changes and its position is
   pinned.
4. Orientations of moved joints are re-derived from the new positions with the adapter's
   `boneFrame` rule, keeping the roll (+Y) of the source joint, so the exported frames always have
   +Z along the bone.
5. **Reset** returns the layer to its source. Edits are kept in the browser's `localStorage`, per
   side, until you reset them or copy a layer again.

### 3.2 Export

**Build edit JSON** fills the text area (**Copy** puts it on the clipboard). Per joint:

| Field | Meaning |
| --- | --- |
| `name` | OpenXR joint name (`palm`, `wrist`, `th_meta` … `lt_tip`). |
| `p_mm` | Position in the wrist frame, millimetres. |
| `delta_mm` | Offset from the source layer. |
| `rot_deg` | Accumulated rotation applied with the buttons (X, Y, Z). |
| `q_xyzw` | Orientation in the wrist frame, derived with the `boneFrame` rule. |
| `p_ovr_root`, `q_ovr_root` | The same pose rotated by `C_hand` into the OVR root frame, i.e. the layout of the adapter's bind table. |

`C_hand` is the per-hand constant OVRPlugin 1.88 uses to convert FB bind poses:
left `(0.7071, 0, −0.7071, 0)`, right `(0, 0.7071, 0, 0.7071)` (x, y, z, w).

## 4. Feeding the edits back into the adapter

The adapter has a built-in table `kEditedBind` in `native/galaxyxr/hand_tracking.inc`. It holds
the **left** hand in the wrist frame (metres, xyzw); the right hand mirrors X, and the adapter
rebuilds every orientation from the positions and the +Y roll of each row. A game converted with
`--hand-bind=edited` uses that table instead of the bind pose derived from the runtime data.

1. Edit the **left** hand and export it (section 3.2). Export the right hand only for comparison.
2. Write the table:

   ```bash
   python -I GXR-update-edited-table.py export.json /path/to/overport-galaxyxr/native/galaxyxr/hand_tracking.inc
   ```

   Only the 26 rows of the table are replaced; running it twice is a no-op.
3. Rebuild the adapter (release, without `GXR_HAND_DIAGNOSTICS`), run the host test and rebuild the CLI:

   ```bash
   bash native/galaxyxr/build.sh
   g++ -std=c++17 -O2 -Wall -Wextra -Werror -Wno-missing-field-initializers -Inative/galaxyxr/include native/galaxyxr/test_hand_tracking.cpp -ldl -pthread -o native/galaxyxr/build/test_hand_tracking && native/galaxyxr/build/test_hand_tracking
   ./gradlew :overportcli:shadowJar
   ```

4. Convert the game with `--hand-bind=edited`, install it and check the hands in the game. To see
   the result in the map, convert with the diagnostics adapter instead and capture again
   (section 1): the new `bind` and `ovrp` layers show what the game now receives.

`samples/hand-edits-left-reference.json` is the reference export that matches the current built-in table; `samples/hand-edits-left-20261014.json` is an earlier version.

## 5. Data file reference

`GXR-hand-map-data.json`: `source` (input file names), `xrNames`/`xrParents` (26 OpenXR joints
and their parents), `ovrNames` (24 OVR bones), `ovrToXr` (OVR bone index to OpenXR joint), and
`sides["0"|"1"]` with:

- `live[]`: `time`, `indexCurl`, `middleCurl` and 26 `joints` (`r` radius, `p`, `q` raw,
  `qAligned` after `alignHandFrames`), world space.
- `bind[]`: 26 joints with `parent`, `r`, `pOvr`/`qOvr` (OVR root frame) and `p`/`q` (wrist frame).
- `ovrp[]`, `meta[]`: 24 bones with `id`/`name`, `parent`, `xr` (matching OpenXR joint),
  `pLocal`/`qLocal` (parent-relative), `pOvr`/`qOvr` (root-relative) and `p`/`q` (wrist frame).

Positions are metres, quaternions are (x, y, z, w).

## License

GPL-3.0, see [LICENSE](LICENSE). The reference capture in `samples/` was recorded on the
author's own headset. `OVRSkeletonData.cs` belongs to Meta and is not distributed here.
