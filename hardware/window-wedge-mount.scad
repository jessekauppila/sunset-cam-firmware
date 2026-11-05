// Window wedge mount for Sunrise/Sunset cameras (Thingino Wyze/Sonoff and similar).
//
// Sticks to the inside of a window with VHB tape. A light-tight hood turns the
// camera a fixed number of degrees left or right of the window's facing, so it
// looks at the equinox sunset (or sunrise) instead of straight out. The setup app
// (/setup/<claim code>) measures the window and tells you which wedge to print:
// 0, 5, 10, 15 or 20 degrees, and which end is tall (north or south).
//
// The hood also seals the camera against the glass, which blocks reflections of
// the room in the window at dusk.
//
// Units: mm. Render: openscad -o mount.stl -D 'wedge_deg=10' -D 'tall_end="right"' window-wedge-mount.scad
//
// CAMERA DIMENSIONS ARE ESTIMATES. Measure your camera's front face and lens
// position with calipers before printing and override the camera_* values.

/* [Wedge (from the setup app)] */
wedge_deg = 10;          // [0:5:20]
// Which end is thick, seen from inside the room looking out the window.
// Facing west, north is on your right; facing east, north is on your left.
tall_end = "right";      // [left, right]

/* [Camera] */
camera = "wyze_v3";      // [wyze_v3, sonoff_s2, custom]
// Used only when camera = "custom":
custom_face_w = 52;      // front face width
custom_face_h = 52;      // front face height
custom_lens_dx = 0;      // lens offset from face centre, + = right (seen from the room)
custom_lens_dy = 6;      // lens offset from face centre, + = up
custom_hfov = 114;       // horizontal field of view, degrees
custom_vfov = 82;        // vertical field of view, degrees

/* [Fit] */
clearance = 0.6;         // pocket clearance per side
wall = 2.4;              // cradle wall thickness
cradle_depth = 16;       // how far the cradle wraps the camera's front
open_bottom = true;      // leave the cradle's bottom open for a stand or cable
plate_t = 2.4;           // plate the camera face rests on
base_t = 2.4;            // flange that sticks to the glass
border = 8;              // VHB margin around the view opening
fov_margin = 4;          // extra degrees on the view cone so the hood never vignettes
strap_slot = [3, 22];    // slots in the side walls for a hook-and-loop strap
lens_window = 16;        // opening at the camera face: lens barrel plus IR/light sensor margin

// ---- camera presets (approximate; measure!) ----
// Wyze Cam v3: ~51 x 51 mm face; FOV 130 deg diagonal, ~114 H x ~82 V (estimated).
// Sonoff CAM-S2: face size unverified; FOV "100 deg" (likely diagonal), ~88 H x ~55 V.
function preset(name) =
    name == "wyze_v3"   ? [52, 52, 0, 6, 114, 82] :
    name == "sonoff_s2" ? [46, 46, 0, 4, 88, 55] :
                          [custom_face_w, custom_face_h, custom_lens_dx, custom_lens_dy, custom_hfov, custom_vfov];

P = preset(camera);
face_w = P[0]; face_h = P[1];
lens_dx = P[2]; lens_dy = P[3];
hfov = P[4]; vfov = P[5];

pocket_w = face_w + 2 * clearance;
pocket_h = face_h + 2 * clearance;
outer_w = pocket_w + 2 * wall;
outer_h = pocket_h + 2 * wall;

// Geometry is built with the tall end on the right (+x) and mirrored if needed.
// Glass is the plane z = 0; the room is +z. The camera plate is hinged at its
// left (thin) edge and rotated by wedge_deg about the vertical (y) axis, so the
// camera's optical axis points out through the glass, turned toward the TALL end
// (the camera's far edge sits further from the glass, so it faces that way).
hinge_x = -outer_w / 2;

module camera_frame() {
    translate([hinge_x, 0, base_t])
        rotate([0, -wedge_deg, 0])
            translate([-hinge_x, 0, 0])
                children();
}

// View cone: a pyramid from the lens out through the glass, sized to the FOV.
module view_cone() {
    L = 200;
    hw = L * tan(min(hfov / 2 + fov_margin, 80));
    hh = L * tan(min(vfov / 2 + fov_margin, 80));
    camera_frame()
        translate([lens_dx, lens_dy, plate_t + 0.01])
            hull() {
                cube([lens_window, lens_window, 0.02], center = true);
                translate([0, 0, -L]) cube([2 * hw, 2 * hh, 0.02], center = true);
            }
}

// Footprint of the view cone on the glass, to size the flange. The camera is
// turned toward the tall end, so the opening on the glass is lopsided: it reaches
// much further on that side. Wide cameras at big wedges would need a huge flange,
// so each side is capped at max_reach; past that, the hood is open on that side
// (some room light can reach the glass there).
max_reach = 60;           // mm from the lens to the flange edge, per side
hh_deg = min(hfov / 2 + fov_margin, 80);
vh_deg = min(vfov / 2 + fov_margin, 80);
lens_rx = lens_dx - hinge_x;                       // lens x measured from the hinge, camera frame
lens_wx = hinge_x + lens_rx * cos(wedge_deg) - plate_t * sin(wedge_deg);
lens_wz = base_t + lens_rx * sin(wedge_deg) + plate_t * cos(wedge_deg);
// Where the view cone's corner and edge rays meet the glass (z = 0), as offsets
// from the lens. A ray that runs nearly parallel to the glass (the tall side of a
// wide camera at a big wedge) is capped at max_reach and left out of the
// vertical sizing, so it can't blow the flange up to a huge height.
function hit_raw(sx, sy) =
    let (dx = sx * tan(hh_deg), dy = sy * tan(vh_deg),
         wx = dx * cos(wedge_deg) + sin(wedge_deg),
         wz = dx * sin(wedge_deg) - cos(wedge_deg),
         t = wz < -0.01 ? lens_wz / -wz : 1e4)
    [t * wx, t * dy];
function capped(h) = abs(h[0]) > max_reach;
function clampv(v) = max(-max_reach, min(max_reach, v));
H = [for (sx = [-1, 0, 1], sy = [-1, 1]) hit_raw(sx, sy)];
Hv = [for (h = H) if (!capped(h)) h];
// The lens window's far edge sits higher off the glass on the tall side.
tall_extra = lens_window * sin(wedge_deg);
foot_x0 = clampv(min([for (h = H) h[0]])) - lens_window / 2;
foot_x1 = clampv(max([for (h = H) h[0]])) + lens_window / 2 + tall_extra;
foot_y0 = clampv(min([for (h = Hv) h[1]])) - lens_window / 2 - tall_extra;
foot_y1 = clampv(max([for (h = Hv) h[1]])) + lens_window / 2 + tall_extra;
lens_wy = lens_dy;
flange_x0 = min(-outer_w / 2, lens_wx + max(foot_x0 - border, -max_reach));
flange_x1 = max(hinge_x + outer_w * cos(wedge_deg), lens_wx + min(foot_x1 + border, max_reach));
flange_y0 = min(-outer_h / 2, lens_wy + max(foot_y0 - border, -max_reach));
flange_y1 = max(outer_h / 2, lens_wy + min(foot_y1 + border, max_reach));

module flange() {
    translate([flange_x0, flange_y0, 0]) cube([flange_x1 - flange_x0, flange_y1 - flange_y0, base_t]);
}

module camera_plate() {
    camera_frame() translate([-outer_w / 2, -outer_h / 2, 0]) cube([outer_w, outer_h, plate_t]);
}

module cradle() {
    camera_frame() translate([0, 0, plate_t - 0.5]) difference() {
        translate([-outer_w / 2, -outer_h / 2, 0]) cube([outer_w, outer_h, cradle_depth + 0.5]);
        // pocket starts at the plate's top face (cradle is sunk 0.5 into the plate for a clean union)
        translate([-pocket_w / 2, -pocket_h / 2, 0.5]) cube([pocket_w, pocket_h, cradle_depth + 2]);
        if (open_bottom)
            translate([-pocket_w / 2 + 6, -outer_h / 2 - 1, 0.5])
                cube([pocket_w - 12, wall + 2, cradle_depth + 2]);
        // strap slots through both side walls
        for (s = [-1, 1])
            translate([s * (outer_w / 2 - wall / 2) - (wall + 2) / 2, -strap_slot[1] / 2, cradle_depth - strap_slot[0] - 2.5])
                cube([wall + 2, strap_slot[1], strap_slot[0]]);
    }
}

module mount() {
    difference() {
        union() {
            // solid wedge between the flange and the camera plate, trimmed so it
            // never rises above the plate the camera face rests on
            intersection() {
                hull() { flange(); camera_plate(); }
                camera_frame() translate([-500, -500, -1000]) cube([1000, 1000, 1000 + plate_t]);
            }
            cradle();
        }
        view_cone();
    }
}

if (tall_end == "right") mount();
else mirror([1, 0, 0]) mount();
