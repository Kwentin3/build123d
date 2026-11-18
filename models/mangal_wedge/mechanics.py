"""Conditional mechanical model of the sketched female V-notch, N and mm.

Two identical faces are both included. Alpha is per face from vertical.
This is not a strength calculation and does not infer dry friction or stiffness.
"""
from dataclasses import dataclass, asdict, replace
import math


@dataclass(frozen=True)
class Case:
    angle_deg: float = 30
    mass_wall_kg: float = 1.8939731976489627  # previous wall, proxy for new wall
    joint_weight_share: float = .5  # two level, equally supporting end joints
    gravity_m_s2: float = 9.80665
    mu_static: float = .3
    mu_seating: float = .3  # impending/sliding envelope; change independently
    gap_mm: float = .6  # NEW notch entrance gap, not old transverse slot
    stop_travel_mm: float = .6  # previous lower-slot vertical freedom
    normal_stiffness_N_mm: float = 1000  # each face; assumed sensitivity only
    guide_mu: float = .3
    guide_normal_N: float = 0  # summed independent bearing preload, NOT inferred from W
    thermal_gap_change_mm: float = 0  # positive opens, negative closes
    retained_extra_normal_N: float = 0  # each face after cooling; scenario, not prediction


def evaluate(c=Case()):
    vals=asdict(c)
    if not all(math.isfinite(v) for v in vals.values()):
        raise ValueError('Finite parameters required')
    if not 0<c.angle_deg<90 or min(c.mass_wall_kg,c.gravity_m_s2,c.normal_stiffness_N_mm)<=0:
        raise ValueError('Positive weight/stiffness and angle in (0,90) required')
    if not 0<c.joint_weight_share<=1 or min(c.mu_static,c.mu_seating,c.guide_mu,c.guide_normal_N,
            c.stop_travel_mm,c.retained_extra_normal_N)<0:
        raise ValueError('Invalid fraction, travel or friction')
    a=math.radians(c.angle_deg); s,co=math.sin(a),math.cos(a)
    W=c.mass_wall_kg*c.gravity_m_s2*c.joint_weight_share
    Fg=c.guide_mu*c.guide_normal_N
    available=W-Fg
    g=c.gap_mm+c.thermal_gap_change_mm
    qc=g/(2*math.tan(a))  # <0 means interference already at entry
    D=s+c.mu_seating*co
    def normal(q): return c.normal_stiffness_N_mm*max(0,q*s-g*co/2)
    start_N=normal(0)
    start_resistance=2*start_N*D+Fg
    # Quasistatic force envelope, with no impact or assumed extra hand pressure.
    if g<0:
        q=0.0; mode='entry_interference_requires_other_assembly_path'
    elif available<=0 or start_resistance>=W:
        q=0.0; mode='blocked_at_entry'
    else:
        qeq=qc+available/(2*c.normal_stiffness_N_mm*s*D)
        q=min(c.stop_travel_mm,max(0,qeq))
        mode='on_final_stop' if qeq>=c.stop_travel_mm else 'on_wedge_before_stop'
    N=normal(q)
    down_resistance=2*N*D+Fg
    Rstop=max(0,W-down_resistance) if mode=='on_final_stop' else 0
    # Extra retained preload is a separate cooling/forced-fit assumption. In a
    # free-gap state no such contact force exists unless deformation also closes
    # that gap; do not silently apply a phantom normal to an unengaged taper.
    extra_applicable=N>0
    Nr=N+(c.retained_extra_normal_N if extra_applicable else 0)
    release_signed=W+Fg+2*Nr*(c.mu_static*co-s)
    # Even a self-releasing taper still requires lifting the wall's weight later.
    lift_peak=max(W+Fg,release_signed)
    at_stop=normal(c.stop_travel_mm)
    force_to_stop=max(0,2*at_stop*D+Fg-W)
    nmin=W/(2*(s+c.mu_static*co))
    denom=2*(s-c.mu_static*co)
    nmax=W/denom if denom>1e-12 else None
    # Free-fall energy envelope: conditional motion with kinetic mu = mu_seating.
    # Two contact springs store K*(u sin a)^2; friction dissipates mu K sin a cos a u^2.
    # Valid only when entry was free and both contacts start together.
    fall=None
    if g>0 and available>0:
        A=c.normal_stiffness_N_mm*s*D
        u=(available+math.sqrt(available**2+4*A*available*qc))/(2*A)
        qpeak=qc+u
        fall={'hypothetical_peak_travel_mm':qpeak,
              'normal_per_face_N':c.normal_stiffness_N_mm*u*s,
              'stop_hit_first':qpeak>=c.stop_travel_mm,
              'status':'NOT_CHECKED' if qpeak>=c.stop_travel_mm else 'CONDITIONAL',
              'reason':'Stop impact stiffness unknown' if qpeak>=c.stop_travel_mm else
                       'Single symmetric compliant energy estimate, no damping calibration'}
    return dict(**vals,weight_per_joint_N=W,guide_friction_N=Fg,
                force_scope='Impending/sliding force envelope, not a unique static friction state',
                extra_retained_preload_applied=extra_applicable,
                release_state_requires_relaxation=release_signed<0,
                angle_friction_deg=math.degrees(math.atan(c.mu_static)),
                self_lock_threshold_mu=math.tan(a),self_locking=c.mu_static>=math.tan(a),
                takeup_slope_mm_per_mm=-2*math.tan(a),first_contact_travel_mm=qc,
                mode=mode,settled_travel_mm=q,
                free_play_mm=max(0,g-2*q*math.tan(a)),
                signed_gap_at_stop_mm=g-2*c.stop_travel_mm*math.tan(a),
                normal_per_face_N=N,retained_normal_per_face_N=Nr,
                tangent_force_per_face_down_N=c.mu_seating*N,
                horizontal_per_face_down_N=N*(co-c.mu_seating*s),
                stop_reaction_N=Rstop,
                force_balance_residual_N=(W-down_resistance-Rstop
                    if mode in ('on_final_stop','on_wedge_before_stop') else None),
                extra_down_force_to_force_stop_N=force_to_stop,
                forced_stop_normal_per_face_N=at_stop,
                initial_up_force_signed_N=release_signed,
                peak_up_force_per_joint_N=lift_peak,
                static_admissible_normal_per_face_N=[nmin,nmax],
                static_range_scope='Equal faces; no guide, no final-stop reaction; not the current general contact state',
                free_fall=fall)


def stop_tolerance_bounds(angle_deg,gap_range=(.3,.9),stroke_range=(.3,.9),angle_error_deg=1):
    lo=angle_deg-angle_error_deg; hi=angle_deg+angle_error_deg
    return dict(angle_deg=angle_deg,
        max_remaining_play_at_stop_mm=max(0,gap_range[1]-2*stroke_range[0]*math.tan(math.radians(lo))),
        max_geometric_interference_at_stop_mm=max(0,2*stroke_range[1]*math.tan(math.radians(hi))-gap_range[0]),
        max_contact_travel_mm=gap_range[1]/(2*math.tan(math.radians(lo))),
        min_contact_travel_mm=gap_range[0]/(2*math.tan(math.radians(hi))))


def sensitivity_cases(base=Case()):
    """One factor at a time; not a probability distribution or reliability claim."""
    factors={
        'mu_static':(.1,.2,.3,.4,.6,.8,1.0),
        'mu_seating':(.1,.3,.6,.8),
        'normal_stiffness_N_mm':(100,1000,10000),
        'gap_mm':(.3,.6,.9),
        'stop_travel_mm':(.3,.6,.9),
        'guide_normal_N':(0,10,30,60),
        'thermal_gap_change_mm':(-.5,-.1,0,.1,.5),
        'retained_extra_normal_N':(0,10,50,100),
        'joint_weight_share':(.25,.5,1),
    }
    cases=[]
    for angle in (20,30,40):
        for factor,values in factors.items():
            for v in values:
                c=replace(base,angle_deg=angle,**{factor:v})
                r=evaluate(c);r.update(varied_parameter=factor,varied_value=v)
                cases.append(r)
        # Correlated stock thickness changes weight AND new notch clearance.
        for t in (2.85,3.0,3.15):
            r=evaluate(replace(base,angle_deg=angle,mass_wall_kg=base.mass_wall_kg*t/3,
                               gap_mm=3.6-t))
            r.update(varied_parameter='actual_stock_thickness_mm',varied_value=t)
            cases.append(r)
    return cases


def short_taper_comparison(base=Case()):
    """Two explicit conditional alternatives, not a production geometry release."""
    # Weight seats on short taper BEFORE a reserve stop. Check stated cold
    # parameter corners; no guide bearing and no thermal distortion are assumed.
    reserve=[]
    for a in (39,41):
        for g in (.3,.9):
            for mu in (.1,.8):
                for k in (100,10000):
                    for share in (.5,1):
                        reserve.append(evaluate(replace(base,angle_deg=a,gap_mm=g,
                            stop_travel_mm=1.2,mu_static=mu,mu_seating=mu,
                            normal_stiffness_N_mm=k,joint_weight_share=share)))
    working_length=1.0
    # A lead-in taper that ends in a positive-clearance straight land and a
    # load-bearing final stop. The land deliberately DOES NOT promise zero play.
    entry_width=4.8; final_width=3.4; t=3.0; tol=.15
    ramp=(entry_width-final_width)/(2*math.tan(math.radians(40)))
    max_ramp=((entry_width+tol)-(final_width-tol))/(2*math.tan(math.radians(39)))
    return dict(
        reserve_stop=dict(angle_deg=40,working_height_mm=working_length,stop_travel_mm=1.2,
            cold_corner_cases=len(reserve),
            max_settled_travel_mm=max(r['settled_travel_mm'] for r in reserve),
            max_normal_per_face_N=max(r['normal_per_face_N'] for r in reserve),
            all_cold_corners_contact_before_working_end=all(
                r['normal_per_face_N']>0 and r['settled_travel_mm']<working_length
                and not r['self_locking'] for r in reserve),
            restrictions='Two equal engaged faces, no loaded guide, no thermal change, no impact; friction/stiffness assumptions unmeasured'),
        load_bearing_stop=dict(angle_deg=40,entrance_width_mm=entry_width,
            final_parallel_width_mm=final_width,nominal_ramp_height_mm=ramp,
            maximum_ramp_height_in_stated_tolerances_mm=max_ramp,
            stop_travel_nominal_mm=1.5,stop_travel_min_mm=1.2,
            final_clearance_min_mm=final_width-tol-(t+tol),
            final_clearance_max_mm=final_width+tol-(t-tol),
            all_tolerances_enter_parallel_land_before_stop=max_ramp<1.2,
            zero_play_guaranteed=False,
            restrictions='Illustrative finished-dimension/stock +/-0.15mm and angle +/-1deg; no residual thermal deformation; positive retaining key still required'))
