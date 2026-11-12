// Adjustable window mount for Sunrise/Sunset cameras (Wyze Cam v3 first).
//
// Two printed parts and one pin, so one mount can ship in the box and be set
// to the window it ends up in:
//
//   frame   A square box that sticks to the inside of the glass with VHB tape.
//           It is the hood that keeps room light off the glass in front of the
//           lens, and its flat top is where the phone rests while aiming.
//   cradle  A sleeve around the front of the camera. It pivots inside the
//           frame about its front corner nearest the glass, so the lens stays
//           close to the glass.
//   pin     Drops through the roof hole marked 0, 10 or 20 and locks the
//           angle. A 3 mm nail or an M3 bolt works in place of a printed pin.
//
// The pivot is hidden. The cradle has a flatted stub top and bottom; hold the
// cradle at entry_a degrees, slide the stubs down the grooves inside the roof
// and floor until they stop, then swing the cradle to its angle. Once it is
// turned away from entry_a the stubs cannot come back out of the grooves.
//
// The camera turns toward the side that swings away from the glass. To turn it
// the other way, turn the whole frame upside down before sticking it on: the
// part is the same top and bottom, so the pivot then sits on the other side.
//
// Three frame styles (same cradle and pin):
//   flat    Double-walled box, flat on all four sides, tape rim on the inside.
//   wings   Single-walled box, flat top and bottom, tape rim left and right.
//   rails   Single-walled box with a tape rim all round, plus a rail along the
//           room edge of the roof and floor at rim height to stand or rest on.
//
// Coordinates: the glass is the plane z = 0 and the room is +z. x runs along
// the glass (to the right, seen from the room), y is up.
//
// Render one part:
//   openscad -o frame.stl  -D 'part="frame"'  window-pivot-mount.scad
//   openscad -o cradle.stl -D 'part="cradle"' window-pivot-mount.scad
//   openscad -o pin.stl    -D 'part="pin"'    window-pivot-mount.scad
// All print without supports: the frame glass-side down, the cradle
// front-down, the pin head-down. Print in PETG or ASA, not PLA (a dark part
// against sunny glass gets hot enough to soften PLA).
//
// CAMERA DIMENSIONS ARE ESTIMATES. Measure the camera's front face with
// calipers before printing and set face_w / face_h.

/* [What to show] */
part = "assembly";       // [assembly, frame, cradle, pin, plate]
style = "flat";          // [flat, wings, rails]
angle = 20;              // [0, 10, 20]
flipped = false;         // assembly only: the frame turned over, pivot on the right
show_camera = true;      // assembly only
show_phone = false;      // assembly only: a phone resting on top
show_view = false;       // assembly only: what the lens sees

/* [Camera] */
face_w = 52;             // front face width
face_h = 52;             // front face height
cam_depth = 58.5;        // front to back
hfov = 102;              // horizontal field of view, degrees (provisional)
vfov = 54;               // vertical field of view, degrees (provisional)

/* [Fit] */
clearance = 0.6;         // camera to sleeve, per side
gap = 0.3;               // cradle to roof and floor, per side
side_wall = 2.4;         // cradle side walls
cap_wall = 3.2;          // cradle top and bottom walls (the pin seats in these)
plate_t = 2.0;           // front plate the camera's face rests on
face_lip = 6;            // how far that plate overlaps the camera's face
sleeve_d = 30;           // how far the cradle wraps the camera, front to back
pin_d = 3.0;
hole_d = 3.5;            // holes in the frame: the pin drops through
socket_d = 3.2;          // hole in the cradle: the pin is snug
head_d = 7;
head_t = 1.2;            // the pin's head sits flush in a counterbore
stub_d = 6;              // hidden pivot stub: diameter,
stub_flat = 3;           //   width across its two flats,
stub_h = 2;              //   and height
entry_a = 30;            // cradle angle at which the stubs slide in and out
flange_t = 2.4;          // thickness of the tape rim
wall = 2.4;              // outer walls
inner_t = 4;             // roof and floor next to the cradle (they hold the grooves)
rim = 10;                // width of the tape rim (3/8 in VHB)
fov_margin = 2;          // extra degrees so the hood never shows in the picture
hood_d = 42;             // how far the box reaches into the room
label_size = 4;

angles = [0, 10, 20];
max_a = max(angles);

// ---- derived ----
pocket_w = face_w + 2 * clearance;
pocket_h = face_h + 2 * clearance;
W = pocket_w + 2 * side_wall;        // cradle outside width
H = pocket_h + 2 * cap_wall;         // cradle outside height
D = sleeve_d;
Hin = H + 2 * gap;                   // clear height between roof and floor
yin = Hin / 2;

// Plan positions in the cradle's own frame: u across (0 = pivot side), w back
// from its front face.
P = [4, 4];                          // pivot
I = [W - 4, 4];                      // locking pin

function rot(v, a) = [v[0] * cos(a) - v[1] * sin(a), v[0] * sin(a) + v[1] * cos(a)];
// The pivot sits just far enough from the glass for the cradle's front corner
// to clear the glass at the largest angle. That corner swings inside the rim's
// opening, so the rim's thickness costs no distance.
zp = P[0] * sin(max_a) + P[1] * cos(max_a) + 0.5;
// Cradle plan point -> frame plan point [x, z] at a given angle.
function place(l, a) = rot(l - P, a) + [0, zp];

// Swinging side: the inside of that wall is an arc about the pivot, so the
// cradle's front plate stays against it at every angle. Its radius is set by
// where the edge of the picture meets the glass at the largest angle.
lens_max = place([W / 2, plate_t], max_a);
x_view = lens_max[0] + 4 + lens_max[1] * tan(min(hfov / 2 + max_a + fov_margin, 80));
Ra = max(norm([W, D] - P) + 1, norm([x_view, zp]));
lip_x = P[0] + sqrt(pow(Ra - 0.8, 2) - P[1] * P[1]) - W;   // front plate reaches the arc
zc = zp + Ra * sin(max_a + 3);       // the arc ends here; square beyond it

// Pivot side: a straight wall, far enough out for the cradle at entry_a and
// for the camera's body at the largest angle.
cam_w = P[1] + (hood_d - zp + sin(max_a)) / cos(max_a);
xi0 = min(place([0, D], entry_a)[0], place([side_wall + clearance, cam_w], max_a)[0]) - 0.8;
xi1 = sqrt(Ra * Ra - zp * zp);
x_open0 = -norm(P) - 0.6;            // the rim's opening starts beside the cradle's corner

flat = style == "flat";
roof_t = flat ? rim : inner_t;
side_t = flat ? rim : wall;
xo0 = xi0 - side_t;
xo1 = xi1 + side_t;
yo = yin + roof_t;
top_y = yo + (style == "rails" ? rim : 0);   // the plane a phone rests on

// Extrude a plan (x, z) shape upward from y0 by h.
module up(y0, h) { translate([0, y0 + h, 0]) rotate([90, 0, 0]) linear_extrude(h) children(); }
module both() { children(); mirror([0, 1, 0]) children(); }

module cavity_plan() {
    intersection() {
        translate([xi0, -1]) square([xi1 - xi0, hood_d + 2]);
        union() {
            translate([0, zp]) circle(r = Ra, $fn = 180);
            translate([xi0, zc]) square([xi1 - xi0, hood_d]);
        }
    }
}

module rounded_plate(x0, x1, y0, y1, t, r = 4) {
    hull() for (x = [x0 + r, x1 - r], y = [y0 + r, y1 - r]) translate([x, y, 0]) cylinder(r = r, h = t, $fn = 32);
}

// What the lens sees, as a solid, with the cradle at angle a.
module view_cone(a) {
    L = 160;
    hw = L * tan(hfov / 2 + fov_margin);
    hh = L * tan(vfov / 2 + fov_margin);
    c = place([W / 2, plate_t], a);
    translate([c[0], 0, c[1]]) rotate([0, -a, 0]) hull() {
        cube([8, 30, 0.02], center = true);
        translate([0, 0, -L]) cube([8 + 2 * hw, 30 + 2 * hh, 0.02], center = true);
    }
}

// Locking holes through roof and floor, counterbored so the head sits flush.
module pin_holes() {
    for (a = angles, s = [-1, 1]) {
        c = place(I, a);
        translate([c[0], s * (yin - 1), c[1]]) rotate([-90 * s, 0, 0]) {
            cylinder(d = hole_d, h = roof_t + 2, $fn = 24);
            translate([0, 0, 1 + roof_t - head_t - 0.2]) cylinder(d = head_d + 0.6, h = head_t + 1, $fn = 32);
        }
    }
}

// Grooves inside the roof and floor that the pivot stubs slide down.
module pivot_seats() {
    both() up(yin - 0.01, stub_h + 0.31) {
        translate([0, zp]) circle(d = stub_d + 0.5, $fn = 32);
        translate([-(stub_flat + 0.4) / 2, zp]) square([stub_flat + 0.4, hood_d]);
    }
}

// Angle numbers beside the locking holes, cut into the roof and the floor.
module labels(top) {
    for (a = angles) {
        c = place(P + (I - P) * 1.15, a);
        translate([c[0], top ? yo - 0.6 : -yo - 0.01, c[1]])
            rotate([90, 0, 0]) translate([0, 0, -0.61])
                linear_extrude(0.62) rotate(a) mirror([0, top ? 1 : 0])
                    text(str(a), size = label_size, halign = "center", valign = "center", font = "Liberation Sans:style=Bold");
    }
}

// flat style: the space between the outer skin and the inner box is hollow,
// with a few ribs across it. It is closed on the room side by a thin cap the
// printer bridges (the widest span is a few millimetres).
module hollow() {
    translate([0, 0, flange_t]) linear_extrude(hood_d - flange_t - 1.2) difference() {
        translate([xo0 + wall, -yo + wall]) square([xo1 - xo0 - 2 * wall, 2 * yo - 2 * wall]);
        translate([xi0 - wall, -yin - inner_t]) square([xi1 - xi0 + 2 * wall, Hin + 2 * inner_t]);
        for (f = [1 / 3, 2 / 3]) translate([xi0 + (xi1 - xi0) * f - 0.8, -yo]) square([1.6, 2 * yo]);
        translate([xo0, -0.8]) square([xo1 - xo0, 1.6]);
    }
}

// rails style: a 45-degree rail along the room edge, as tall as the rim.
module rail() {
    translate([xo0, yo, 0]) rotate([90, 0, 90]) linear_extrude(xo1 - xo0)
        polygon([[0, hood_d - rim - 2], [0, hood_d], [rim, hood_d], [rim, hood_d - 2]]);
}

module frame() {
    ey = style == "rails" ? rim : 0;
    difference() {
        union() {
            difference() {
                translate([xo0, -yo, 0]) cube([xo1 - xo0, 2 * yo, hood_d]);
                up(-yin, Hin) cavity_plan();
            }
            // the rim covers the glass between the pivot-side wall and the cradle
            translate([xi0 - 0.01, -yin - 0.01, 0]) cube([x_open0 - xi0, Hin + 0.02, flange_t]);
            if (!flat) difference() {
                rounded_plate(xo0 - rim, xo1 + rim, -yo - ey, yo + ey, flange_t);
                translate([xo0, -yo, -1]) cube([xo1 - xo0, 2 * yo, flange_t + 2]);
            }
            if (style == "rails") both() rail();
        }
        if (flat) hollow();
        pivot_seats();
        pin_holes();
        labels(true);
        labels(false);
        for (a = angles) view_cone(a);
    }
}

// The cradle in its own frame: x = u, y up (centred), z = w.
module cradle_local() {
    ow = face_w - 2 * face_lip;
    oh = face_h - 2 * face_lip;
    difference() {
        union() {
            translate([0, -H / 2, 0]) cube([W, H, D]);
            translate([W - 0.01, -H / 2, 0]) cube([lip_x, H, plate_t]);
            // pivot stubs: round, with two flats that line up with the frame's
            // grooves only when the cradle is at entry_a
            translate([P[0], 0, P[1]]) both() up(H / 2 - 0.01, stub_h) intersection() {
                circle(d = stub_d, $fn = 32);
                rotate(-entry_a) square([stub_flat, stub_d + 1], center = true);
            }
        }
        translate([side_wall, -pocket_h / 2, plate_t]) cube([pocket_w, pocket_h, D]);
        translate([W / 2 - ow / 2, -oh / 2, -1]) cube([ow, oh, plate_t + 2]);
        translate([I[0], 0, I[1]]) rotate([90, 0, 0]) cylinder(d = socket_d, h = H + 2, center = true, $fn = 24);
    }
}

module camera_local() {
    translate([side_wall + clearance, -face_h / 2, plate_t]) {
        color("white") cube([face_w, face_h, cam_depth]);
        color("#111") translate([face_w / 2, face_h / 2, -0.4]) cylinder(d = 26, h = 0.5, $fn = 48);
    }
}

module pin() {
    cylinder(d = head_d, h = head_t, $fn = 32);
    cylinder(d = pin_d, h = roof_t + gap + cap_wall - 0.6, $fn = 24);
}

// A phone lying on top with its long edge against the glass.
module phone() { translate([(xo0 + xo1) / 2 - 74, top_y, 0.5]) cube([148, 8, 72]); }

module in_frame(a) { translate([0, 0, zp]) rotate([0, -a, 0]) translate([-P[0], 0, -P[1]]) children(); }
module pin_in_frame(a) { c = place(I, a); translate([c[0], yo, c[1]]) rotate([90, 0, 0]) pin(); }

module assembly() {
    color("#3a3a3a") frame();
    color("#8a8a8a") in_frame(angle) cradle_local();
    if (show_camera) in_frame(angle) camera_local();
    color("#f5a344") pin_in_frame(angle);
    if (show_phone) color("#222") phone();
    if (show_view) color("#f5a344", 0.18) view_cone(angle);
}

echo(style = style, width = xo1 - xo0 + (flat ? 0 : 2 * rim), height = 2 * top_y, depth = hood_d,
     lens0 = place([W / 2, plate_t], 0)[1], lens20 = lens_max[1], xi0 = xi0, xi1 = xi1, Ra = Ra, zp = zp);

if (part == "frame") frame();
else if (part == "cradle") cradle_local();
else if (part == "pin") pin();
else if (part == "plate") {
    frame();
    translate([xo1 + rim + 8, 0, 0]) cradle_local();
    for (i = [0:1]) translate([xo0 + 8 + i * 12, -top_y - 10, 0]) pin();
}
else if (part == "assembly") {
    if (flipped) rotate([0, 0, 180]) assembly();
    else assembly();
}
