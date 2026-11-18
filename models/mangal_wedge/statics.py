"""Rigid planar Coulomb statics, independent of CAD geometry.

Coordinates are X/Z in mm, forces in N, moment x*Fz-z*Fx in N mm.
Normal reactions are unilateral. Feasibility does not establish retained
preload, contact engagement, elastic compatibility, or real load capacity.
An unbounded LP is an undetermined rigid self-stress, never infinite strength.
"""

from dataclasses import dataclass
from math import cos, isfinite, radians, sin
from typing import Mapping, Sequence

import numpy as np
from scipy.optimize import linprog


@dataclass(frozen=True)
class Contact:
    name: str
    position: tuple[float, float]
    normal: tuple[float, float]
    tangent: tuple[float, float]
    mu: float

    def __post_init__(self):
        if not self.name or not all(isfinite(v) for v in (*self.position, *self.normal, *self.tangent, self.mu)):
            raise ValueError("Contact requires a name and finite coordinates")
        if self.mu < 0:
            raise ValueError("Friction coefficient must be nonnegative")
        if not np.isclose(np.linalg.norm(self.normal), 1) or not np.isclose(np.linalg.norm(self.tangent), 1):
            raise ValueError("Contact directions must be unit vectors")
        if not np.isclose(np.dot(self.normal, self.tangent), 0):
            raise ValueError("Normal and tangent must be perpendicular")


@dataclass(frozen=True)
class StaticResult:
    status: str
    forces: dict[str, tuple[float, float]]  # normal N, signed tangent T
    upward_load: float | None
    objective: float | None
    residual: tuple[float, float, float] | None
    message: str

    @property
    def feasible(self) -> bool:
        return self.status == "feasible"


def wedge_contacts(alpha_deg: float, mu: float, thickness: float = 3.0) -> tuple[Contact, Contact]:
    """Moving female notch; alpha is the flank angle FROM VERTICAL."""
    if not 0 < alpha_deg < 90 or not isfinite(thickness) or thickness <= 0:
        raise ValueError("Require 0 < alpha < 90 degrees and positive thickness")
    a = radians(alpha_deg)
    return (
        Contact("left", (-thickness / 2, 0), (-cos(a), sin(a)), (sin(a), cos(a)), mu),
        Contact("right", (thickness / 2, 0), (cos(a), sin(a)), (-sin(a), cos(a)), mu),
    )


def lower_shoulder(direction: int, mu: float = 0, drop: float = 80) -> Contact:
    """Optional effective X shoulder, NOT the old slot's Y side wall.

    Include only a physically engaged shoulder. No preload is imposed.
    """
    if direction not in (-1, 1) or not isfinite(drop) or drop <= 0:
        raise ValueError("Require direction +/-1 and positive drop")
    return Contact("guide", (0, -drop), (direction, 0), (0, 1), mu)


def lower_stop(drop: float = 80, mu: float = 0) -> Contact:
    """Optional engaged upward stop, able to bypass the wedge load path."""
    if not isfinite(drop) or drop <= 0:
        raise ValueError("Require positive drop")
    return Contact("stop", (0, -drop), (0, 1), (1, 0), mu)


def _solve(contacts: Sequence[Contact], weight: float, eccentricity: float,
           upward: float, fixed_normals: Mapping[str, float] | None,
           objective_contact: str | None = None, maximize: bool = False,
           vary_upward: bool = False) -> StaticResult:
    contacts = tuple(contacts)
    names = [c.name for c in contacts]
    if not contacts or len(set(names)) != len(names):
        raise ValueError("Require contacts with unique names")
    if not all(isfinite(v) for v in (weight, eccentricity, upward)) or weight < 0 or upward < 0:
        raise ValueError("Require finite loads, nonnegative weight and upward force")
    fixed_normals = dict(fixed_normals or {})
    if set(fixed_normals) - set(names) or any(not isfinite(v) or v < 0 for v in fixed_normals.values()):
        raise ValueError("Fixed normals require existing contact names and nonnegative finite values")
    if objective_contact is not None and objective_contact not in names:
        raise ValueError("Unknown objective contact")
    count = 2 * len(contacts) + int(vary_upward)
    equilibrium = np.zeros((3, count))
    cone = np.zeros((2 * len(contacts), count))
    bounds = []
    for i, contact in enumerate(contacts):
        x, z = contact.position
        for j, (fx, fz) in enumerate((contact.normal, contact.tangent)):
            equilibrium[:, 2*i+j] = (fx, fz, x*fz-z*fx)
        cone[2*i, 2*i:2*i+2] = (-contact.mu, 1)
        cone[2*i+1, 2*i:2*i+2] = (-contact.mu, -1)
        fixed = fixed_normals.get(contact.name)
        bounds.extend(((0, None) if fixed is None else (fixed, fixed), (None, None)))
    target = np.array((0, weight - upward, weight * eccentricity))
    objective = np.zeros(count)
    if vary_upward:
        equilibrium[1, -1] = 1
        target[1] = weight
        bounds.append((0, None))
        objective[-1] = -1
    elif objective_contact is not None:
        objective[2 * names.index(objective_contact)] = -1 if maximize else 1
    else:
        # Select the least total normal among feasible states.
        objective[0:2*len(contacts):2] = 1
    result = linprog(objective, A_ub=cone, b_ub=np.zeros(len(cone)),
                     A_eq=equilibrium, b_eq=target, bounds=bounds, method="highs")
    if result.status == 2:
        return StaticResult("infeasible", {}, None, None, None, result.message)
    if result.status == 3:
        return StaticResult("unbounded", {}, None, None, None,
                            "Rigid Coulomb problem is unbounded; retained preload and elastic compatibility are unspecified. This is not infinite physical capacity.")
    if not result.success:
        raise RuntimeError(f"Statics LP failed: {result.message}")
    reactions = {name: tuple(float(v) for v in result.x[2*i:2*i+2]) for i, name in enumerate(names)}
    value = -result.fun if (maximize or vary_upward) else result.fun
    return StaticResult("feasible", reactions, float(result.x[-1]) if vary_upward else upward,
                        float(value), tuple(float(v) for v in equilibrium @ result.x-target), result.message)


def solve_equilibrium(contacts: Sequence[Contact], weight: float, eccentricity: float = 0,
                      upward: float = 0, fixed_normals: Mapping[str, float] | None = None) -> StaticResult:
    """Find unilateral equilibrium; choose minimum summed normal reaction."""
    return _solve(contacts, weight, eccentricity, upward, fixed_normals)


def normal_range(contacts: Sequence[Contact], weight: float, contact: str,
                 eccentricity: float = 0, upward: float = 0,
                 fixed_normals: Mapping[str, float] | None = None) -> tuple[StaticResult, StaticResult]:
    """Minimum/maximum feasible normal of one contact, including unbounded status."""
    return tuple(_solve(contacts, weight, eccentricity, upward, fixed_normals, contact, maximum)
                 for maximum in (False, True))


def maximum_upward_load(contacts: Sequence[Contact], weight: float,
                        fixed_normals: Mapping[str, float], eccentricity: float = 0) -> StaticResult:
    """Maximum upward force at x=0 for explicitly retained normal reactions.

    fixed_normals are an assumption supplied by the caller, not a preload proof.
    Unspecified reactions remain free, so callers should inspect unbounded status.
    """
    if not fixed_normals:
        raise ValueError("Specify retained normals explicitly")
    return _solve(contacts, weight, eccentricity, 0, fixed_normals, vary_upward=True)
