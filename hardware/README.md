# Printed window mount for Thingino cameras

`window-wedge-mount.scad` is a one-piece, light-tight hood that sticks to the
inside of a window with VHB tape and holds a Wyze Cam v3, Sonoff CAM-S2 (or any
camera you give dimensions for) turned 0–20° left or right of the window's
facing. It's the printed counterpart of the Pi's wedge bracket: the setup app
(`/setup/<claim code>`) measures the window and prints the exact settings on its
"Print and fit the mount" step, e.g.

```sh
openscad -o mount.stl -D 'wedge_deg=5' -D 'tall_end="left"' -D 'camera="wyze_v3"' window-wedge-mount.scad
```

- **`wedge_deg`**: 0, 5, 10, 15 or 20.
- **`tall_end`**: the thick end, seen from inside looking out. The camera turns toward the thick end.
- **`camera`**: `wyze_v3`, `sonoff_s2`, or `custom` with the `custom_*` values.

**Measure first.** The camera face sizes and lens positions in the presets are
estimates (no official drawings). Check the face width/height and where the lens
sits with calipers, and adjust `custom_*` or the preset, before printing. Print a
0° one first to check the fit.

What was checked (by rendering every wedge and ray-casting the view cone):

- The camera's full field of view clears the hood at every wedge, for both presets, mirrored or not.
- The camera axis turns by exactly `wedge_deg` toward `tall_end`.
- The meshes are watertight.
- The glass-side opening keeps a ≥8 mm tape border on every side, except one case: the Wyze v3 (≈114° wide) at 15° and 20°. There, the view on the thick side runs nearly parallel to the glass, so the opening reaches the edge on that side. The mount still works, but room light can reach the glass on that side. Raise `max_reach` for a bigger flange if reflections show up.

Print: PETG or ASA (it sits in a sunny window), flange face down, 0.2 mm layers, no supports needed for 0–10°. Strap the camera in through the side slots with a hook-and-loop strap.
