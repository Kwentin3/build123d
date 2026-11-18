"""The shared rear-cover joint; prototype dimensions in mm, +Z rear.

The purchased screws are nominal envelopes, not printable parts. Thread-forming
contact in the blind pilot is intentional; physical PETG fit is not certified.
"""

SCREW_CENTRES = ((-33.5, -33.5), (-33.5, 33.5), (33.5, -33.5), (33.5, 33.5))
COVER_THICKNESS = 5.0
BOSS_DIAMETER = 10.0
BOSS_LENGTH = 14.0
PILOT_DIAMETER = 2.4
PILOT_DEPTH = 12.0
SCREW_DIAMETER = 3.0
SCREW_LENGTH = 12.0
SCREW_HEAD_DIAMETER = 5.3
SCREW_HEAD_HEIGHT = 2.3
COVER_CLEARANCE = 3.5
HEAD_POCKET_DIAMETER = 8.0
HEAD_POCKET_DEPTH = 2.6
UNDER_HEAD_RELIEF_DIAMETER = 4.2
UNDER_HEAD_RELIEF_DEPTH = .5
WALL_SCREW_X = (-50.0, 50.0)
KEY_ENTRY_Y = 8.0
KEY_END_Y = 16.0
KEY_ENTRY_DIAMETER = 10.0
KEY_NECK = 4.6
WALL_SCREW_DIAMETER = 4.0
WALL_SCREW_LENGTH = 25.0
WALL_HEAD_DIAMETER = 7.9
WALL_HEAD_HEIGHT = 2.8
WALL_STANDOFF = .5
TEST_BOARD_THICKNESS = 30.0

from build123d import Box, Cone, Cylinder, Pos


def cylinder(diameter, z0, z1, x=0, y=0):
    return Pos(x, y, (z0 + z1)/2) * Cylinder(diameter/2, z1-z0)


def cover_hole(lid, rear_z, x, y):
    seat = rear_z + COVER_THICKNESS - HEAD_POCKET_DEPTH
    lid -= cylinder(COVER_CLEARANCE, rear_z-1, rear_z+COVER_THICKNESS+1, x, y)
    lid -= cylinder(HEAD_POCKET_DIAMETER, seat, rear_z+COVER_THICKNESS+1, x, y)
    lid -= Pos(x, y, seat-UNDER_HEAD_RELIEF_DEPTH/2) * Cone(
        COVER_CLEARANCE/2, UNDER_HEAD_RELIEF_DIAMETER/2, UNDER_HEAD_RELIEF_DEPTH)
    return lid


def add_rear_joint(body, lid, rear_z):
    """One joint owner for all three explicitly shaped housings/covers."""
    for x, y in SCREW_CENTRES:
        body += cylinder(BOSS_DIAMETER, rear_z-BOSS_LENGTH, rear_z, x, y)
        body -= cylinder(PILOT_DIAMETER, rear_z-PILOT_DEPTH, rear_z+1, x, y)
        lid = cover_hole(lid, rear_z, x, y)
    return body, lid


def cover_hardware(rear_z):
    seat = rear_z + COVER_THICKNESS - HEAD_POCKET_DEPTH
    hardware = {}
    for index, (x, y) in enumerate(SCREW_CENTRES, 1):
        screw = cylinder(SCREW_DIAMETER, seat-SCREW_LENGTH, seat, x, y)
        screw += cylinder(SCREW_HEAD_DIAMETER, seat, seat+SCREW_HEAD_HEIGHT, x, y)
        screw.label = f"cover_screw_{index}"
        hardware[screw.label] = screw
    return hardware


def wall_keyholes(lid, rear_z):
    z0, z1 = rear_z-1, rear_z+COVER_THICKNESS+1
    for x in WALL_SCREW_X:
        cut = cylinder(KEY_ENTRY_DIAMETER, z0, z1, x, KEY_ENTRY_Y)
        cut += cylinder(KEY_NECK, z0, z1, x, KEY_END_Y)
        cut += Pos(x, (KEY_ENTRY_Y+KEY_END_Y)/2, (z0+z1)/2) * Box(
            KEY_NECK, KEY_END_Y-KEY_ENTRY_Y, z1-z0)
        lid -= cut
    return lid


def wall_hardware(rear_z):
    # Clock lowered until a nominal 4mm shank touches the end of the 4.6mm slot.
    y = KEY_END_Y + (KEY_NECK-WALL_SCREW_DIAMETER)/2
    hardware = {}
    for index, x in enumerate(WALL_SCREW_X, 1):
        screw = cylinder(WALL_SCREW_DIAMETER, rear_z, rear_z+WALL_SCREW_LENGTH, x, y)
        screw += cylinder(WALL_HEAD_DIAMETER, rear_z-WALL_HEAD_HEIGHT, rear_z, x, y)
        screw.label = f"wall_screw_{index}"
        hardware[screw.label] = screw
    return hardware


def coupon():
    """Three separate pilot choices, printed and tested with the real screw."""
    base = Pos(0, 0, 1.5) * Box(48, 18, 3)
    base -= Pos(-23, 8, 1.5) * Box(2, 2, 5)
    lid = Pos(0, 0, 19.5) * Box(48, 18, COVER_THICKNESS)
    for x, diameter in ((-15, 2.3), (0, 2.4), (15, 2.5)):
        base += cylinder(BOSS_DIAMETER, 3, 17, x)
        base -= cylinder(diameter, 5, 18, x)
        lid = cover_hole(lid, 17, x, 0)
    base.label = "pilot_coupon_2p3_2p4_2p5_left_to_right"
    lid.label = "coupon_cover_same_grip_as_product"
    return dict(body=base, lid=lid)
