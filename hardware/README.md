# Printed window mounts for Thingino cameras

## Adjustable mount: `window-pivot-mount.scad` (current design, not yet printed)

One mount ships with every camera and is set to the window it ends up in, so
nobody prints a wedge per window. Three printed parts:

- **frame**: a square box that sticks to the glass with VHB tape. It is the
  light hood, it stands flat on a sill, and a phone lies flat on its top
  against the glass while aiming.
- **cradle**: a sleeve around the front of the camera. It pivots inside the
  frame about its front corner nearest the glass, on a hidden pivot.
- **pin**: drops through the roof hole marked 0, 10 or 20 and sits flush. A
  3 mm nail or an M3 bolt also works.

To turn the camera the other way, turn the frame upside down before sticking
it on. To fit the cradle, hold it at 30°, slide its stubs down the grooves
inside the roof and floor, then swing it to its angle.

```sh
openscad -o frame.stl  -D 'part="frame"'  window-pivot-mount.scad
openscad -o cradle.stl -D 'part="cradle"' window-pivot-mount.scad
openscad -o pin.stl    -D 'part="pin"'    window-pivot-mount.scad
```

`style` picks the frame: `flat` (the chosen design: flat on all four sides,
tape rim on the inside, 106 × 80 × 42 mm), `wings` or `rails`.

Checked in the model only: the cradle clears the frame at 0, 10, 20 and 30°,
and the pivot stubs cannot leave their grooves at 0, 10 or 20°.

Not checked: nothing has been printed. The camera size (52 × 52 × 58.5 mm) is
an estimate, so measure the face with calipers and set `face_w` / `face_h`
first. The pivot stubs hold by about 0.5 mm, which is tight for a home printer.
The camera's stand is assumed removed and its cable assumed to leave at the
rear; neither has a slot. Print in PETG or ASA, frame glass-side down, cradle
front-down, no supports.

## Fixed wedge: `window-wedge-mount.scad` (earlier design)

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
