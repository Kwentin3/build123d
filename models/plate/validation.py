"""Measured checks for this centred rectangular plate, not a general CAD validator."""

import math

from build123d import GeomType
from OCP.BRepCheck import BRepCheck_Analyzer

LENGTH_TOL_MM = 1e-6
VOLUME_ABS_TOL_MM3 = 1e-3
VOLUME_REL_TOL = 1e-8
CHECK_NAMES = (
    "occ_valid", "solid_count", "dimensions", "thickness", "hole_diameter",
    "hole_position", "through_hole", "volume",
)


def check_plate(plate, expected):
    """Measure native topology and compare it with the caller's engineering intent."""
    width, height, thickness, diameter = (
        expected[key] for key in ("width", "height", "thickness", "hole_diameter")
    )
    size = plate.bounding_box().size
    solids = plate.solids()
    cylinders = plate.faces().filter_by(GeomType.CYLINDER)
    rims = plate.edges().filter_by(GeomType.CIRCLE)
    dimensions = [size.X, size.Y, size.Z]
    rim_centres = [list(edge.arc_center) for edge in rims]
    bore_diameters = [2 * face.radius for face in cylinders]
    planar_z = [face.center().Z for face in plate.faces().filter_by(GeomType.PLANE)
                if abs(abs(face.normal_at().Z) - 1) <= LENGTH_TOL_MM]
    measured_thickness = max(planar_z) - min(planar_z) if len(planar_z) >= 2 else None
    actual = {"dimensions_mm": dimensions, "volume_mm3": plate.volume,
              "solid_count": len(solids), "thickness_mm": measured_thickness,
              "bore_diameters_mm": bore_diameters, "rim_centres_mm": rim_centres}
    checks = {}

    def record(name, passed, observed, target, tolerance=None):
        checks[name] = {"status": "PASS" if passed else "FAIL",
                        "actual": observed, "expected": target}
        if tolerance is not None:
            checks[name]["tolerance"] = tolerance

    def close(a, b):
        return math.isclose(a, b, rel_tol=0, abs_tol=LENGTH_TOL_MM)

    valid = bool(BRepCheck_Analyzer(plate.wrapped).IsValid())
    record("occ_valid", valid, valid, True)
    record("solid_count", len(solids) == 1, len(solids), 1)
    record("dimensions", all(close(a, b) for a, b in zip(dimensions, (width, height, thickness))),
           dimensions, [width, height, thickness], {"absolute_mm": LENGTH_TOL_MM})
    record("thickness", measured_thickness is not None and close(measured_thickness, thickness),
           measured_thickness, thickness, {"absolute_mm": LENGTH_TOL_MM})
    record("hole_diameter", len(cylinders) == 1 and close(bore_diameters[0], diameter),
           bore_diameters, [diameter], {"absolute_mm": LENGTH_TOL_MM})
    centred = len(rims) == 2 and all(close(c[0], 0) and close(c[1], 0) for c in rim_centres)
    record("hole_position", centred, [c[:2] for c in rim_centres], [[0, 0], [0, 0]],
           {"absolute_mm": LENGTH_TOL_MM})
    # Use topology AND solid point classification, independently of Box-Cylinder code.
    rim_z = sorted(c[2] for c in rim_centres)
    open_rims = len(rims) == 2 and all(close(a, b) for a, b in zip(rim_z, (-thickness / 2, thickness / 2)))
    bore_spans_z = len(cylinders) == 1 and close(cylinders[0].bounding_box().size.Z, thickness)
    axis_empty = len(solids) == 1 and all(
        not solids[0].is_inside((0, 0, z)) for z in (-thickness * 0.49, 0, thickness * 0.49)
    )
    record("through_hole", open_rims and bore_spans_z and axis_empty,
           {"rim_z_mm": rim_z, "bore_spans_thickness": bore_spans_z, "axis_empty": axis_empty},
           {"rim_z_mm": [-thickness / 2, thickness / 2], "bore_spans_thickness": True, "axis_empty": True},
           {"absolute_mm": LENGTH_TOL_MM})
    # Analytic area of rectangle minus disk, independent of CAD boolean operations.
    expected_volume = (width * height - math.pi * diameter**2 / 4) * thickness
    record("volume", math.isclose(plate.volume, expected_volume,
                                   rel_tol=VOLUME_REL_TOL, abs_tol=VOLUME_ABS_TOL_MM3),
           plate.volume, expected_volume,
           {"absolute_mm3": VOLUME_ABS_TOL_MM3, "relative": VOLUME_REL_TOL})
    return actual, checks
