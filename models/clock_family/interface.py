"""The one shared socket for TFA 60.3065.02; mm, +Z towards the rear.

Published installation envelope, NOT a replica of the purchased clock/ring.
See SOURCES.md for source quality and unverified retention.
"""

from math import isfinite

from build123d import Cylinder, Pos

INSTALL_DIAMETER = 77.0
INSTALL_DEPTH = 22.0
BEZEL_DIAMETER = 90.0
OVERALL_DEPTH = 36.0
DIAMETRAL_ALLOWANCE = 0.4  # prototype choice, not an OEM tolerance
CHANGE_ALLOWANCE = 1.0


def socket_cut(allowance=DIAMETRAL_ALLOWANCE):
    if not isfinite(allowance) or not 0 <= allowance <= 2:
        raise ValueError("Prototype diametral allowance must be finite, 0..2 mm")
    return Pos(0, 0, INSTALL_DEPTH / 2) * Cylinder(
        (INSTALL_DIAMETER + allowance) / 2, INSTALL_DEPTH)


def installation_envelope():
    return Pos(0, 0, INSTALL_DEPTH / 2) * Cylinder(
        INSTALL_DIAMETER / 2, INSTALL_DEPTH)
