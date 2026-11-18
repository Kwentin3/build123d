"""Teaching filter-cartridge holder; mm, X across, Y up, Z out of its backing.

Nominal geometry only. Function and service requirements live in README.md.
No material, fabrication or strength approval is implied.
"""

CARTRIDGE_WIDTH = 50.0
CARTRIDGE_HEIGHT = 70.0
CARTRIDGE_DEPTH = 8.0
CARTRIDGE_Z = 10.0
FRAME_WIDTH = 74.0
FRAME_HEIGHT = 94.0
RAIL_WIDTH = 10.0
FRAME_DEPTH = 18.0
CROSSBAR_Y = 42.0
CROSSBAR_HEIGHT = 6.0
CROSSBAR_Z = 10.0

from build123d import Box, Pos


def make_holder(crossbar_z=CROSSBAR_Z):
    backing = Box(FRAME_WIDTH, FRAME_HEIGHT, 2)
    frame = backing
    for x in (-32, 32):
        frame += Pos(x, 0, 10) * Box(RAIL_WIDTH, FRAME_HEIGHT, FRAME_DEPTH)
    frame += Pos(0, -39, 10) * Box(FRAME_WIDTH, 8, FRAME_DEPTH)
    frame += Pos(0, CROSSBAR_Y, crossbar_z) * Box(
        FRAME_WIDTH, CROSSBAR_HEIGHT, FRAME_DEPTH)
    cartridge = Pos(0, 0, CARTRIDGE_Z) * Box(
        CARTRIDGE_WIDTH, CARTRIDGE_HEIGHT, CARTRIDGE_DEPTH)
    frame.label = "frame"
    cartridge.label = "cartridge"
    return dict(frame=frame, cartridge=cartridge)
