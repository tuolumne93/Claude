// Parametric children's tableware — plate, bowl, cup, spoon and suction cup.
//
// Open in OpenSCAD and use the Customizer (Window > Customizer). The
// "parameter set" dropdown holds age-group presets generated from
// age_presets.json by `python cad/build.py --customizer`.
// For batch export use cad/build.py.
// All dimensions in millimetres.

/* [Product] */
product = "plate"; // [plate, bowl, cup, spoon, suction_cup]
// Wall / shell thickness
wall = 3; // [1.5:0.5:6]
// Rendering smoothness
$fn = 96; // [32:16:192]

/* [Plate] */
plate_diameter = 200; // [140:5:260]
plate_rim_height = 25; // [10:1:40]
// Number of food sections (1 = no dividers)
plate_sections = 3; // [1:1:5]
// "half_split" = one large half + small sections; "radial" = equal wedges
plate_layout = "half_split"; // [half_split, radial]
// Divider height as a fraction of rim height
divider_ratio = 0.8; // [0.4:0.05:1]

/* [Bowl] */
bowl_diameter = 130; // [80:5:200]
bowl_height = 55; // [30:1:90]

/* [Cup] */
cup_diameter = 65; // [45:1:90]
cup_height = 75; // [50:1:120]
cup_handles = 2; // [0:1:2]
// Extra base thickness for a low centre of gravity
cup_base = 6; // [2:1:15]

/* [Vessel shape (plate, bowl, cup)] */
// How far the wall leans outward from base to rim
flare = 8; // [0:1:30]
// Inward lip at the rim to push food onto the utensil (0 = none)
scoop_lip = 3; // [0:0.5:8]
// Radius of the inside floor-to-wall fillet (bigger = easier scooping & cleaning)
inner_fillet = 8; // [0:1:25]
floor_thickness = 3; // [1.5:0.5:8]

/* [Suction mount] */
suction_mount = true;
// Inner diameter of the socket on the underside
suction_socket_d = 60; // [30:1:120]
suction_socket_h = 6; // [3:0.5:12]
// Outer diameter of the flexible suction skirt (suction_cup product)
suction_skirt_d = 110; // [50:1:200]

/* [Spoon] */
spoon_bowl_length = 35; // [20:1:60]
spoon_bowl_width = 26; // [15:1:45]
spoon_bowl_depth = 6; // [2:0.5:15]
spoon_handle_length = 90; // [50:1:160]
// Grip thickness at the handle end (chunky = easier palmar grasp)
spoon_grip_d = 16; // [8:1:30]
// Rise of the handle end above the bowl rim
spoon_handle_rise = 10; // [0:1:30]
// Flange behind the bowl that limits how far the spoon can go in the mouth
gag_guard = true;
gag_guard_d = 40; // [30:1:60]

/* [Hidden] */
eps = 0.01;

// ---------------------------------------------------------------------------

module vessel(D, H) {
    R = D / 2;            // outer radius at the rim
    Rb = R - flare;       // outer radius at the base
    union() {
        // floor
        cylinder(r = Rb - wall / 2, h = floor_thickness);
        // wall + rim + scoop lip + inner fillet, as one revolved profile
        rotate_extrude() {
            hull() {
                translate([Rb - wall, 0]) square([wall, eps]);
                translate([R - wall / 2, H - wall / 2]) circle(d = wall);
            }
            if (scoop_lip > 0)
                hull() {
                    translate([R - wall / 2, H - wall / 2]) circle(d = wall);
                    translate([R - wall / 2 - scoop_lip, H - wall / 2]) circle(d = wall);
                }
            if (inner_fillet > 0) {
                f = min(inner_fillet, H - floor_thickness - wall);
                x0 = Rb - wall + flare * f / H;  // inner wall position just above floor
                translate([x0 - f, floor_thickness])
                    difference() {
                        square([f + eps, f]);
                        translate([0, f]) circle(r = f);
                    }
            }
        }
    }
}

// Inner radius of a flared vessel at height z
function inner_r(D, H, z) = D / 2 - flare - wall + flare * z / H;

module divider(len, h) {
    hull() {
        translate([0, -wall / 2, 0]) cube([len, wall, eps]);
        translate([0, 0, h - wall / 2]) rotate([0, 90, 0]) cylinder(d = wall, h = len);
    }
}

module plate_dividers(D, H) {
    dh = H * divider_ratio;
    L = D / 2;
    intersection() {
        cylinder(r1 = inner_r(D, H, 0) + 1, r2 = inner_r(D, H, dh) + 1, h = dh);
        union() {
            if (plate_sections > 1 && plate_layout == "radial")
                for (i = [0 : plate_sections - 1])
                    rotate([0, 0, 90 + i * 360 / plate_sections]) divider(L, dh);
            if (plate_sections > 1 && plate_layout == "half_split") {
                // full-width divider separating the large half
                translate([-L, 0, 0]) divider(2 * L, dh);
                // split the other half into (sections - 1) parts
                if (plate_sections > 2) for (k = [1 : plate_sections - 2])
                    rotate([0, 0, 180 * k / (plate_sections - 1)]) divider(L, dh);
            }
        }
    }
}

module suction_socket() {
    // Ring on the underside; a 1 mm inward lip at the opening retains the
    // flange of the flexible suction cup.
    translate([0, 0, -suction_socket_h])
        difference() {
            cylinder(d = suction_socket_d + 2 * wall, h = suction_socket_h + eps);
            translate([0, 0, 1]) cylinder(d = suction_socket_d, h = suction_socket_h);
            translate([0, 0, -eps]) cylinder(d = suction_socket_d - 2, h = 1 + 2 * eps);
        }
}

module plate() {
    vessel(plate_diameter, plate_rim_height);
    plate_dividers(plate_diameter, plate_rim_height);
    if (suction_mount) suction_socket();
}

module bowl() {
    vessel(bowl_diameter, bowl_height);
    if (suction_mount) suction_socket();
}

module cup() {
    R = cup_diameter / 2;
    union() {
        // thick base for stability, then the vessel on top of it
        cylinder(r = R - flare - wall / 2, h = cup_base);
        translate([0, 0, cup_base - floor_thickness]) vessel(cup_diameter, cup_height - cup_base + floor_thickness);
        if (cup_handles > 0) {
            hr = cup_height * 0.22;        // handle loop radius
            hd = max(10, wall * 3.5);      // handle bar thickness
            for (i = [0 : cup_handles - 1])
                rotate([0, 0, i * 180])
                    translate([R - flare * 0.45 - wall, 0, cup_height * 0.5])
                        rotate([90, 0, 0]) rotate([0, 0, -90])
                            rotate_extrude(angle = 180)
                                translate([hr, 0]) scale([0.7, 1]) circle(d = hd);
        }
    }
}

module spoon() {
    L = spoon_bowl_length; W = spoon_bowl_width; D = spoon_bowl_depth;
    t = max(1.5, wall * 0.6);
    rim_z = D + t;
    neck_d = max(7, t * 4);
    union() {
        // concave bowl, sitting on the build plate
        translate([0, 0, rim_z])
            difference() {
                scale([L / 2 + t, W / 2 + t, D + t]) sphere(1);
                scale([L / 2, W / 2, D]) sphere(1);
                translate([-L, -W, 0]) cube([2 * L, 2 * W, D + t + 1]);
            }
        // handle: neck to an oval, anti-roll grip
        hull() {
            translate([L / 2, 0, rim_z - neck_d / 2]) scale([1, 1, 0.6]) sphere(d = neck_d);
            translate([L / 2 + spoon_handle_length, 0, rim_z - neck_d / 2 + spoon_handle_rise])
                scale([1.5, 1, 0.7]) sphere(d = spoon_grip_d);
        }
        if (gag_guard)
            translate([L / 2 + 12, 0, rim_z - neck_d / 2 + spoon_handle_rise * 12 / spoon_handle_length])
                rotate([0, 90, 0]) scale([0.6, 1, 1]) cylinder(d = gag_guard_d, h = 3, center = true);
    }
}

module suction_cup() {
    // Flexible part (silicone / TPU). Flange snaps into suction_socket().
    flange_d = suction_socket_d - 0.4;
    neck_d = suction_socket_d - 2.4;
    skirt_h = 7;
    st = 1.6;  // skirt thickness
    // built upside-down for printing: skirt on the bed
    difference() {
        cylinder(d1 = suction_skirt_d, d2 = neck_d, h = skirt_h);
        translate([0, 0, -eps]) cylinder(d1 = suction_skirt_d - 2 * st, d2 = neck_d - 2 * st - 4, h = skirt_h - st);
    }
    translate([0, 0, skirt_h - eps]) cylinder(d = neck_d, h = 1 + eps);
    translate([0, 0, skirt_h + 1]) cylinder(d = flange_d, h = suction_socket_h - 1.4);
}

// Echo key numbers for build.py (volume of food space in ml).
function frustum_ml(r1, r2, h) = PI * h / 3 * (r1 * r1 + r1 * r2 + r2 * r2) / 1000;

if (product == "plate") {
    plate();
    echo(str("CAPACITY_ML=", frustum_ml(inner_r(plate_diameter, plate_rim_height, floor_thickness),
                                         inner_r(plate_diameter, plate_rim_height, plate_rim_height),
                                         plate_rim_height - floor_thickness)));
} else if (product == "bowl") {
    bowl();
    echo(str("CAPACITY_ML=", frustum_ml(inner_r(bowl_diameter, bowl_height, floor_thickness),
                                         inner_r(bowl_diameter, bowl_height, bowl_height),
                                         bowl_height - floor_thickness)));
} else if (product == "cup") {
    cup();
    ch = cup_height - cup_base + floor_thickness;
    echo(str("CAPACITY_ML=", frustum_ml(inner_r(cup_diameter, ch, floor_thickness),
                                         inner_r(cup_diameter, ch, ch), ch - floor_thickness)));
} else if (product == "spoon") {
    spoon();
    echo(str("CAPACITY_ML=", 2 / 3 * PI * spoon_bowl_length / 2 * spoon_bowl_width / 2 * spoon_bowl_depth / 1000));
} else if (product == "suction_cup") {
    suction_cup();
}
