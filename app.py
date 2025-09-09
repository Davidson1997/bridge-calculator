from flask import Flask, render_template, request, make_response
import math
import logging
from weasyprint import HTML

app = Flask(__name__)
logging.basicConfig(level=logging.DEBUG)

# Make built-in zip available in Jinja2 templates
app.jinja_env.globals.update(zip=zip)

def get_float(value, default=0.0):
    """Safely convert a value to float."""
    try:
        return float(value.strip()) if value and isinstance(value, str) else default
    except Exception:
        return default

def get_additional_load_sf(load_material):
    """Return the safety factor for an additional load based on its material."""
    if not load_material:
        return 1.0
    material = load_material.strip().lower()
    if material == "steel":
        return 1.05
    elif material in ["concrete", "timber"]:
        return 1.15
    else:
        return 1.0

# ---------------- Steel Calculations ----------------
def calculate_steel_capacity(steel_grade, flange_width, flange_thickness, web_thickness, web_depth, condition_factor):
    steel_grade = steel_grade.strip()
    fy = 230.0 if steel_grade == "S230" else (275.0 if steel_grade == "S275" else 355.0)
    overall_depth = web_depth + 2 * flange_thickness  # overall depth in mm
    Z_plastic = (flange_width * flange_thickness * (overall_depth - flange_thickness) +
                 (web_thickness * (overall_depth - 2 * flange_thickness)**2) / 4) # in mm³
    Mpe = (fy * (Z_plastic/1e6))  # kNm
    shear_capacity = (fy * web_thickness * overall_depth * condition_factor) / (1.73 * 1.05 * 1.1 * 1000)  # kN
    logging.debug(f"Steel: overall_depth={overall_depth} mm, Z_plastic={Z_plastic:.6f} m³, Mpe={Mpe:.6f} kNm, shear={shear_capacity:.6f} kN")
    return Mpe, shear_capacity

# ---------------- Concrete Calculations ----------------
def calculate_concrete_capacity(concrete_grade, beam_width, total_depth, reinforcement_layers,
                                reinforcement_strength, condition_factor,
                                partial_factor_concrete=1.5, partial_factor_reinf=1.15,
                                partial_factor_shear=1.25):
    if concrete_grade == "C32/40":
        f_ck = 30
        fcu = 40
    else:
        f_ck = 40
        fcu = 50
    f_cd = f_ck / partial_factor_concrete
    f_y = reinforcement_strength
    f_y_design = f_y / partial_factor_reinf

    total_As = 0.0
    weighted_depth = 0.0
    for num, dia, cover in zip(
        request.form.getlist("reinforcement_num[]"),
        request.form.getlist("reinforcement_diameter[]"),
        request.form.getlist("reinforcement_cover[]")
    ):
        if num != "" and dia != "" and cover != "":
            cover_val = get_float(cover)
            if cover_val >= total_depth:
                raise ValueError("Invalid reinforcement cover: cover must be less than total depth.")
            A_layer = int(num) * (math.pi / 4) * (get_float(dia) ** 2)
            total_As += A_layer
            d_layer = total_depth - (cover_val + get_float(dia) / 2)
            weighted_depth += A_layer * d_layer
    if total_As == 0:
        raise ValueError("No reinforcement provided. Please enter valid reinforcement details.")
    d_eff = weighted_depth / total_As
    z_calculated = d_eff * (1 - (0.84 * (f_y / 1.15) * total_As) / ((fcu / 1.5) * beam_width * d_eff))
    z = min(z_calculated, 0.95 * d_eff)
    
    Mus = (f_y_design * total_As * z) / 1e6  # kNm
    Muc = (0.225 * (fcu / 1.5) * beam_width * (d_eff ** 2)) / 1e6  # kNm
    moment_capacity = min(Mus, Muc) * condition_factor
    
    Ss = (550 / d_eff) ** 0.25
    if Ss > 1.0:
        Ss = 1.0
    vc = (0.24 / partial_factor_shear) * (((100 * total_As) / (beam_width * d_eff)) ** 0.333 * (fcu ** 0.333))
    Vu = Ss * vc * beam_width * d_eff
    Vu_kN = Vu / 1000.0
    logging.debug(f"Concrete: f_ck={f_ck}, fcu={fcu}, f_cd={f_cd:.2f}, f_y_design={f_y_design:.2f}")
    logging.debug(f"Reinf: total_As={total_As:.2f} mm², weighted_depth={weighted_depth:.2f} mm, d_eff={d_eff:.2f} mm, z_calculated={z_calculated:.2f} mm, z={z:.2f} mm")
    logging.debug(f"Mus = {Mus:.6f} kNm, Muc = {Muc:.6f} kNm, chosen moment_capacity = {moment_capacity:.6f} kNm")
    logging.debug(f"Ultimate Shear: Ss = {Ss:.4f}, vc = {vc:.4f}, Vu = {Vu_kN:.6f} kN")
    
    return moment_capacity, Vu_kN, Mus, Muc, d_eff, total_As

# ---------------- Timber Calculations ----------------
def calculate_timber_beam(form_data):
    timber_beam_width = get_float(form_data.get("timber_beam_width"))
    timber_beam_depth = get_float(form_data.get("timber_beam_depth"))
    timber_grade = form_data.get("timber_grade")
    timber_K3 = get_float(form_data.get("timber_K3"))
    timber_K2 = 0.8
    timber_K7 = (300 / timber_beam_depth) ** 0.11 if timber_beam_depth > 0 else 0

    timber_properties = {
         "C16": {"bending_parallel": 16.0, "shear_parallel": 1.8},
         "C24": {"bending_parallel": 24.0, "shear_parallel": 2.5},
         "D40": {"bending_parallel": 40.0, "shear_parallel": 4.0},
         "D50": {"bending_parallel": 50.0, "shear_parallel": 4.0},
         "GL28c": {"bending_parallel": 28.0, "shear_parallel": 3.2},
         "GL28h": {"bending_parallel": 28.0, "shear_parallel": 2.7},
         "Birch": {"bending_parallel": 26.1, "shear_parallel": 2.6}
    }
    props = timber_properties.get(timber_grade, {"bending_parallel": 16.0, "shear_parallel": 1.8})
    bending_parallel = props["bending_parallel"]
    shear_parallel = props["shear_parallel"]

    b1 = bending_parallel * timber_K2 * timber_K3 * timber_K7
    b2 = shear_parallel * timber_K2 * timber_K3 * timber_K7

    Z = (timber_beam_width * (timber_beam_depth ** 2)) / 6.0
    timber_moment_capacity = (Z * b1) / 1e6
    timber_shear_capacity = (b2 * timber_beam_width * timber_beam_depth) / 1e3

    timber_results = {
        "Timber Beam Width (mm)": timber_beam_width,
        "Timber Beam Depth (mm)": timber_beam_depth,
        "Timber Grade": timber_grade,
        "Modification Factor K2": timber_K2,
        "Modification Factor K3": timber_K3,
        "Modification Factor K7": timber_K7,
        "B1 (MPa)": round(b1, 3),
        "B2 (MPa)": round(b2, 3),
        "Timber Bending Capacity (kNm)": round(timber_moment_capacity, 3),
        "Timber Shear Capacity (kN)": round(timber_shear_capacity, 3)
    }
    return timber_results

# ---------------- Other Functions ----------------
def calculate_effective_length(L, k1=1.0, k2=1.0):
    return k1 * k2 * L

def calculate_radius_of_gyration_strong(B_f, t_f, t_w, web_depth):
    d = web_depth + 2 * t_f
    A = 2 * (B_f * t_f) + t_w * (d - 2 * t_f)
    I_x = (t_w ** 3 * (d - 2 * t_f)) / 12.0 + 2 * ((t_f * (B_f ** 3)) / 12.0)
    r_x = math.sqrt(I_x / A)
    logging.debug(f"Strong axis: A={A} mm², I_x={I_x} mm⁴, r_x={r_x} mm")
    return r_x / 1000.0

# --- K4 helpers (add these; do not remove existing functions) ---
def section_props_for_k4(B_f, t_f, t_w, web_depth_mm):
    """
    Inputs in mm. Returns:
      A_mm2, d_mm (overall), h_mm (flange-centre spacing), Ix_mm4 (major), Iy_mm4 (minor)
    """
    d = web_depth_mm + 2 * t_f
    h = d - 2 * t_f
    A = 2 * (B_f * t_f) + t_w * (d - 2 * t_f)

    Ix_web = (t_w * (d - 2*t_f)**3) / 12.0
    Ix_fl  = 2 * ((B_f * t_f**3) / 12.0 + (B_f * t_f) * ((d/2 - t_f/2)**2))
    Ix = Ix_web + Ix_fl

    Iy = 2 * ((t_f * B_f**3) / 12.0) + ((d - 2*t_f) * t_w**3) / 12.0

    return A, d, h, Ix, Iy

def k4_minor_axis(Z_plastic_mm3, A_mm2, h_mm, Ix_mm4, Iy_mm4):
    if A_mm2 <= 0 or h_mm <= 0 or Ix_mm4 <= 0:
        return 1.0

    ratio = 1.0 - (Iy_mm4 / Ix_mm4)
    if ratio <= 0:
        return 1.0

    val = (4.0 * (Z_plastic_mm3 ** 2) / (A_mm2 ** 2 * h_mm ** 2)) * ratio
    val = max(val, 0.0)

    return val ** 0.25

lookup_table = {
    0: 1.000000,
    40: 0.900000,
    50: 0.798750,
    60: 0.700000,
    70: 0.580000,
    80: 0.550000,
    90: 0.500000,
    100: 0.450000,
    110: 0.400000,
    120: 0.350000,
    130: 0.320000,
    140: 0.300000,
    150: 0.280000,
    160: 0.260000,
    170: 0.240000,
    180: 0.220000,
    190: 0.200000,
    200: 0.180000
}

def get_lookup_factor(X):
    keys = sorted(lookup_table.keys())
    if X <= keys[0]:
        return lookup_table[keys[0]]
    if X >= keys[-1]:
        return lookup_table[keys[-1]]
    for i in range(len(keys)-1):
        if keys[i] <= X <= keys[i+1]:
            fraction = (X - keys[i]) / (keys[i+1] - keys[i])
            factor = lookup_table[keys[i]] + fraction * (lookup_table[keys[i+1]] - lookup_table[keys[i]])
            logging.debug(f"X={X}, Lookup Factor={factor}")
            return factor
    return 1.0

def calculate_v_from_F(F):
    table = {
        0: 1.000000,
        1: 0.988000,
        2: 0.956000,
        3: 0.912000,
        4: 0.864000,
        5: 0.817000,
        6: 0.774000,
        7: 0.734000,
        8: 0.699000,
        9: 0.668000,
        10: 0.639000,
        11: 0.614000,
        12: 0.591000,
        13: 0.571000,
        14: 0.552000,
        15: 0.535000,
        16: 0.519000,
        17: 0.505000,
        18: 0.492000,
        19: 0.479000,
        20: 0.468000
    }
    if F <= 0:
        return 1.0
    if F >= 20:
        return table[20]
    lower = int(math.floor(F))
    upper = lower + 1
    fraction = F - lower
    v_val = table[lower] + fraction * (table[upper] - table[lower])
    logging.debug(f"F={F}, v={v_val}")
    return v_val

def calculate_slenderness(effective_length, web_depth, flange_thickness, B_f, t_w, k4=1.0):
    r = calculate_radius_of_gyration_strong(B_f, flange_thickness, t_w, web_depth)
    d = web_depth + 2 * flange_thickness
    F_param = (effective_length * flange_thickness) / (r * d)
    v = calculate_v_from_F(F_param)
    slenderness = (effective_length / r) * v * k4
    logging.debug(f"Effective Length={effective_length}, r={r}, F={F_param}, v={v}, k4={k4}, slenderness={slenderness}")
    return slenderness, F_param, v, r

def calculate_bd37_moment_capacity(Mpe, effective_length, steel_grade, flange_width, flange_thickness, web_thickness, web_depth, k4=1.0):
    fy = 230.0 if steel_grade.strip() == "S230" else (275.0 if steel_grade.strip() == "S275" else 355.0)
    slenderness, F_param, v_value, r = calculate_slenderness(effective_length, web_depth, flange_thickness, flange_width, web_thickness, k4=k4)
    X = slenderness * math.sqrt(fy / 355.0) if Mpe != 0 else 0.0
    lookup_factor = get_lookup_factor(X)
    MR = (lookup_factor * Mpe * condition factor) / (1.05 * 1.1)
    logging.debug(f"Steel: fy={fy}, slenderness={slenderness}, X={X}, k4={k4}, Lookup Factor={lookup_factor}, MR={MR}")
    return MR, slenderness, X


def calculate_vehicle_loads(span_length, vehicle_type, impact_factor=1.0, wheel_dispersion="none", axle_mode="per beam"):
    vt = vehicle_type.strip().lower()
    if vt == "3 tonne":
        spacing = 2.0
        P1 = 21.0
        P2 = 9.0
    elif vt == "7.5 tonne":
        spacing = 2.0
        P1 = 59.0
        P2 = 15.0
    elif vt == "18 tonne":
        spacing = 3.0
        P1 = 64.0
        P2 = 113.0
    else:
        return {"Vehicle Maximum Moment (kNm)": 0.0, "Vehicle Maximum Shear (kN)": 0.0}
    if axle_mode.strip().lower() == "per beam":
        P1 /= 2.0
        P2 /= 2.0
    P1 *= 1.3
    P2 *= 1.3
    reduction_factor = 1.0
    try:
        rd = float(wheel_dispersion)
        if rd == 25:
            reduction_factor = 0.75
        elif rd == 50:
            reduction_factor = 0.5
    except:
        reduction_factor = 1.0
    P1 *= reduction_factor
    P2 *= reduction_factor
    worst_M = 0.0
    worst_V = 0.0
    a_step = 0.01
    x_step = 0.01
    L = span_length
    for a in drange(0, L - spacing, a_step):
        b = a + spacing
        R_A = (P1 * (L - a) + P2 * (L - b)) / L
        M_max_for_a = 0.0
        V_max_for_a = 0.0
        x = 0.0
        while x <= L:
            if x <= a:
                M = R_A * x
            elif x <= b:
                M = R_A * x - P1 * (x - a)
            else:
                M = R_A * x - P1 * (x - a) - P2 * (x - b)
            if x < a:
                V = R_A
            elif x < b:
                V = R_A - P1
            else:
                V = R_A - P1 - P2
            M_max_for_a = max(M_max_for_a, abs(M))
            V_max_for_a = max(V_max_for_a, abs(V))
            x += x_step
        worst_M = max(worst_M, M_max_for_a)
        worst_V = max(worst_V, V_max_for_a)
    worst_M *= impact_factor
    worst_V *= impact_factor
    return {"Vehicle Maximum Moment (kNm)": worst_M, "Vehicle Maximum Shear (kN)": worst_V}

def calculate_applied_loads(span_length, loading_type, additional_loads, loaded_width=None, access_factor=None, lane_width=None):
    if loading_type == "HA":
        base_udl = 230 * (1 / span_length)**0.67
        if loaded_width is None or loaded_width <= 0:
            loaded_width = 3.65
        if access_factor is None:
            access_factor = 1.3
        effective_udl = ((base_udl * 0.76) / (3.65 / 2.5)) * (loaded_width / 2.5) * access_factor
        base_kel = 82
        kel = ((base_kel * 0.76) / (3.65 / 2.5)) * (loaded_width / 2.5) * access_factor
        base_moment = (effective_udl * span_length**2) / 8 + (kel * span_length) / 4
        base_shear = (effective_udl * span_length) / 2 + (kel) / 2
        default_loads = {"base_udl": base_udl, "effective_udl": effective_udl, "kel": kel}
    elif loading_type == "HB":
        udl = 45
        point_load = 180
        if loaded_width is not None and access_factor is not None:
            effective_udl = ((udl * 0.76) / (3.65 / 2.5)) * (loaded_width / 2.5) * access_factor
        else:
            effective_udl = udl
        default_loads = {"udl": udl, "effective_udl": effective_udl}
        base_moment = (effective_udl * span_length**2) / 8 + (point_load * span_length) / 4
        base_shear = (effective_udl * span_length) / 2 + point_load / 2
    else:
        base_moment = 0
        base_shear = 0
        default_loads = {"udl": 0, "effective_udl": 0}
    
    additional_dead = 0.0
    additional_live = 0.0
    additional_shear = 0.0
    applied_load_breakdown = "\nApplied Load Calculation Process:\n----------------------------------\n"
    applied_load_breakdown += f"Base UDL = {base_udl:.3f} kN/m, Loaded Width = {loaded_width}, Access Factor = {access_factor}\n"
    applied_load_breakdown += f"Effective UDL = {default_loads.get('effective_udl'):.3f} kN/m, HA KEL = {default_loads.get('kel'):.3f} kN\n"
    applied_load_breakdown += f"Base Moment = {base_moment:.3f} kNm, Base Shear = {base_shear:.3f} kN\n"
    for load in additional_loads:
        try:
            load_value = load.get("value", 0)
            distribution = load.get("load_distribution", "").lower()
            if not distribution:
                distribution = ""
            load_type_str = load.get("type", "").lower() or "live"
            load_material = load.get("load_material", "steel").lower()
            if distribution == "udl":
                add_moment = (load_value * span_length**2) / 8
                add_shear = (load_value * span_length) / 2
            elif distribution == "point":
                add_moment = (load_value * span_length) / 4
                add_shear = load_value / 2
            else:
                add_moment = 0
                add_shear = 0
            if load_type_str == "dead":
                sf = get_additional_load_sf(load_material)
                additional_dead += add_moment * sf
                applied_load_breakdown += f"Additional Dead Load ({load['description']}): {load_value} with SF {sf} => Moment: {add_moment*sf:.3f} kNm, Shear: {add_shear:.3f} kN\n"
            else:
                additional_live += add_moment
                applied_load_breakdown += f"Additional Live Load ({load['description']}): {load_value} => Moment: {add_moment:.3f} kNm, Shear: {add_shear:.3f} kN\n"
            additional_shear += add_shear
        except Exception as e:
            logging.error(f"Error processing additional load: {load} - {e}")
    total_applied_moment = base_moment + additional_dead + additional_live
    total_applied_shear = (default_loads.get("effective_udl", 0) * span_length) / 2 + (kel if loading_type=="HA" else 0) + additional_shear
    applied_load_breakdown += f"Total Applied Moment = {total_applied_moment:.3f} kNm, Total Applied Shear = {total_applied_shear:.3f} kN\n"
    return total_applied_moment, total_applied_shear, default_loads, additional_dead, additional_live, applied_load_breakdown

def calculate_beam_capacity(form_data, loads):
    material = form_data.get("material")
    condition_factor = get_float(form_data.get("condition_factor"), 1.0)
    span_length = get_float(form_data.get("span_length"))
    L_actual = get_float(form_data.get("effective_member_length"), span_length)
    k1 = get_float(form_data.get("k1"), 1.0)
    k2 = get_float(form_data.get("k2"), 1.0)
    effective_length = calculate_effective_length(L_actual, k1, k2)
    loading_type = form_data.get("loading_type")

    loaded_width = get_float(form_data.get("loaded_width"), 3.65)
    access_str = form_data.get("access_type", "Company")
    access_factor = 1.5 if access_str.lower() == "public" else 1.3

    calculation_process = ""
    # Predeclare to avoid NameErrors in result section
    shear_capacity = 0.0
    k4 = 1.0

    if material == "Steel":
        steel_grade = form_data.get("steel_grade")
        flange_width = get_float(form_data.get("flange_width"))
        flange_thickness = get_float(form_data.get("flange_thickness"))
        web_thickness = get_float(form_data.get("web_thickness"))
        web_depth = get_float(form_data.get("beam_depth"))

        # Base section capacity (returns Mpe, shear)
        Mpe, shear_capacity = calculate_steel_capacity(
            steel_grade, flange_width, flange_thickness, web_thickness, web_depth, condition_factor
        )

        # Compute Z_plastic locally (m^3) for reporting AND for k4
        overall_depth = web_depth + 2 * flange_thickness
        Z_plastic = (
            flange_width * flange_thickness * (overall_depth - flange_thickness)
            + (web_thickness * (overall_depth - 2 * flange_thickness) ** 2) / 4
        ) 

        # k4 (minor-axis symmetric I/L-section)
        A_mm2, d_mm, h_mm, Ix_mm4, Iy_mm4 = section_props_for_k4(
            flange_width, flange_thickness, web_thickness, web_depth
        )

        k4 = k4_minor_axis(Z_plastic, A_mm2, h_mm, Ix_mm4, Iy_mm4)
        logging.debug(f"Section props for k4: A={A_mm2:.1f} mm², d={d_mm:.1f} mm, h={h_mm:.1f} mm, Ix={Ix_mm4:.1f} mm⁴, Iy={Iy_mm4:.1f} mm⁴")
        logging.debug(f"Z_plastic input to k4 (m³)={Z_plastic:.6e}, converted to mm³={Z_plastic*1e9:.1f}")
        logging.debug(f"Calculated k4 = {k4:.3f}")

        # BD37 capacity using k4
        try:
            MR, slenderness, X = calculate_bd37_moment_capacity(
                Mpe, effective_length, steel_grade,
                flange_width, flange_thickness, web_thickness, web_depth,
                k4=k4
            )
            moment_capacity = MR
        except Exception as e:
            logging.error("Error in BD37 capacity calculation: %s", e)
            slenderness, _, _, _ = calculate_slenderness(
                effective_length, web_depth, flange_thickness, flange_width, web_thickness, k4=k4
            )
            fy_fallback = 230.0 if steel_grade.strip() == "S230" else (275.0 if steel_grade.strip() == "S275" else 355.0)
            X = slenderness * math.sqrt(fy_fallback / 355.0) if Mpe != 0 else 0.0
            moment_capacity = Mpe  # fallback to plastic

        # Breakdown text
        calculation_process += "Steel Beam Calculation Process:\n----------------------------------\n"
        calculation_process += f"Steel Grade: {steel_grade}\n"
        calculation_process += f"Flange: Width = {flange_width} mm, Thickness = {flange_thickness} mm\n"
        calculation_process += f"Web: Thickness = {web_thickness} mm, Depth = {web_depth} mm\n"
        calculation_process += f"Overall Depth = {web_depth} + 2 x {flange_thickness} = {overall_depth} mm\n"
        calculation_process += f"Plastic Section Modulus, Z_plastic = {Z_plastic:.6f} m³\n"
        fy = 230.0 if steel_grade.strip() == "S230" else (275.0 if steel_grade.strip() == "S275" else 355.0)
        calculation_process += f"Yield Strength, fy = {fy} N/mm²\n"
        calculation_process += f"k4 (minor-axis symmetry) = {k4:.3f}\n"
        calculation_process += f"Mpe = (fy x Z_plastic)  = {Mpe:.3f} kNm\n"
        calculation_process += f"Slenderness = {slenderness:.3f}, X = {X:.3f}\n"
        calculation_process += f"Lookup Factor = {get_lookup_factor(X):.3f}\n"
        calculation_process += f"Adjusted Moment Capacity, MR = Lookup Factor x Mpe x condition factor / (1.05 x 1.1) = {moment_capacity:.3f} kNm\n"
        calculation_process += "----------------------------------\n"

    elif material == "Concrete":
        concrete_grade = form_data.get("concrete_grade")
        beam_width = get_float(form_data.get("beam_width"))
        total_depth = get_float(form_data.get("concrete_beam_depth"))
        if total_depth == 0:
            total_depth = get_float(form_data.get("beam_depth"))

        reinforcement_nums = request.form.getlist("reinforcement_num[]")
        reinforcement_diameters = request.form.getlist("reinforcement_diameter[]")
        reinforcement_covers = request.form.getlist("reinforcement_cover[]")
        reinforcement_strength = get_float(form_data.get("reinforcement_strength"), 500.0)

        reinforcement_layers = []
        for num, dia, cover in zip(reinforcement_nums, reinforcement_diameters, reinforcement_covers):
            if num != "" and dia != "" and cover != "":
                reinforcement_layers.append({
                    "num_bars": int(num),
                    "bar_diameter": get_float(dia),
                    "layer_cover": get_float(cover)
                })
        if not reinforcement_layers:
            return {"error": "No reinforcement provided. Please enter valid reinforcement details."}

        try:
            moment_capacity_conc, shear_capacity, Mus, Muc, d_eff, total_As = calculate_concrete_capacity(
                concrete_grade, beam_width, total_depth, reinforcement_layers,
                reinforcement_strength=reinforcement_strength, condition_factor=condition_factor
            )
        except Exception as e:
            return {"error": str(e)}

        moment_capacity = moment_capacity_conc
        effective_depth = d_eff

        calculation_process += "Concrete Beam Calculation Process:\n----------------------------------\n"
        calculation_process += f"Concrete Grade: {concrete_grade}\n"
        calculation_process += f"Beam Width = {beam_width} mm, Total Depth = {total_depth} mm\n"
        calculation_process += f"Effective Depth (d_eff) = {effective_depth:.3f} mm\n"
        calculation_process += f"Total Reinforcement Area = {total_As:.3f} mm²\n"
        calculation_process += f"Mus (Reinforcement Moment) = {Mus:.3f} kNm\n"
        calculation_process += f"Muc (Concrete Moment) = {Muc:.3f} kNm\n"
        calculation_process += f"Chosen Moment Capacity = min(Mus, Muc) x condition factor = {moment_capacity:.3f} kNm\n"
        calculation_process += "----------------------------------\n"

    elif material == "Timber":
        timber_results = calculate_timber_beam(form_data)
        moment_capacity = timber_results.get("Timber Bending Capacity (kNm)")
        shear_capacity = timber_results.get("Timber Shear Capacity (kN)")
        calculation_process += "Timber Beam Calculation Process:\n----------------------------------\n"
        calculation_process += f"Timber Grade: {form_data.get('timber_grade')}\n"
        calculation_process += f"Beam Width = {form_data.get('timber_beam_width')} mm, Beam Depth = {form_data.get('timber_beam_depth')} mm\n"
        calculation_process += f"Calculated Bending Capacity = {moment_capacity} kNm\n"
        calculation_process += "----------------------------------\n"

    else:
        moment_capacity = 0.0
        shear_capacity = 0.0
        calculation_process = "No calculation process available.\n"

    # Effective length reduction for capacity (your original behaviour)
    reduction_factor = 1.0
    if effective_length < span_length:
        reduction_factor = effective_length / span_length
        moment_capacity *= reduction_factor

    applied_moment, applied_shear, default_loads, additional_dead, additional_live, load_breakdown = \
        calculate_applied_loads(span_length, loading_type, loads, loaded_width, access_factor)

    # Self weight for steel
    self_weight_moment = 0.0
    if material == "Steel":
        A_steel = 2 * (flange_width * flange_thickness) + web_thickness * web_depth
        self_weight = (A_steel / 1e6) * 7850 * 9.81 / 1000  # kN/m
        self_weight_moment = ((self_weight * span_length ** 2) / 8) * 1.05  # include 1.05

    total_applied_moment = applied_moment + self_weight_moment
    utilisation_ratio = total_applied_moment / moment_capacity if moment_capacity > 0 else float('inf')
    pass_fail = "Pass" if moment_capacity >= total_applied_moment and shear_capacity >= applied_shear else "Fail"

    applied_live = applied_moment - additional_dead
    applied_dead = additional_dead + self_weight_moment

    calculation_process += load_breakdown

    result = {
        "Span Length (m)": round(span_length, 1),
        "Effective Member Length (m)": round(effective_length, 1),
        "k1": round(k1, 1),
        "k2": round(k2, 1),
        "Reduction Factor": round(reduction_factor, 1),
        "Moment Capacity (kNm)": round(moment_capacity, 1),
        "Shear Capacity (kN)": round(shear_capacity, 1),
        "Applied Moment (ULS) (kNm)": round(total_applied_moment, 1),
        "Applied Shear (ULS) (kN)": round(applied_shear, 1),
        "Applied Live Load Moment (kNm)": round(applied_live, 1),
        "Applied Dead Load Moment (kNm)": round(applied_dead, 1),
        "Self Weight Moment (kNm)": round(self_weight_moment, 1),
        "Utilisation Ratio": round(utilisation_ratio, 1) if utilisation_ratio != float('inf') else "N/A",
        "Pass/Fail": pass_fail,
        "Loading Type": loading_type,
        "Condition Factor": round(condition_factor, 1),
        "Loaded Carriageway Width (m)": round(loaded_width, 1),
        "Access Type": access_str,
        "Calculation Process": calculation_process
    }

    if material == "Steel":
        slenderness_disp, F_param_disp, v_disp, r_disp = calculate_slenderness(
            effective_length, web_depth, flange_thickness, flange_width, web_thickness, k4=k4
        )
        result["k4 (minor-axis)"] = round(k4, 3)
        result["Slenderness (λ)"] = round(slenderness_disp, 1)
        result["X Parameter"] = round(
            slenderness_disp * math.sqrt((230 if steel_grade == "S230" else (275 if steel_grade == "S275" else 355)) / 355.0),
            1
        )

    if material == "Concrete":
        result["Mus (kNm)"] = round(Mus, 1)
        result["Muc (kNm)"] = round(Muc, 1)
        result["Effective Depth (mm)"] = round(effective_depth, 1)
        result["Total Reinforcement Area (mm²)"] = round(total_As, 1)

    if material == "Timber":
        result.update(timber_results)

    if loading_type in ["HA", "HB"]:
        result[f"{loading_type} UDL (kN/m)"] = round(default_loads.get("effective_udl", 0), 1)
    if loading_type == "HA":
        result["HA KEL (kN)"] = round(default_loads.get("kel", 0), 1)

    vehicle_type = form_data.get("vehicle_type", "").strip()
    vehicle_impact_factor = get_float(form_data.get("vehicle_impact_factor"), 1.0)
    wheel_dispersion = form_data.get("wheel_dispersion", "none").strip()
    axle_mode = form_data.get("axle_load_mode", "per beam").strip()
    if vehicle_type and vehicle_type.lower() != "none":
        vehicle_results = calculate_vehicle_loads(span_length, vehicle_type, vehicle_impact_factor, wheel_dispersion, axle_mode)
        vehicle_results = {k: round(v, 1) for k, v in vehicle_results.items()}
        result.update(vehicle_results)

    result["Additional Loads"] = loads
    logging.debug("Calculation result: %s", result)
    return result

def drange(start, stop, step):
    r = start
    while r <= stop:
        yield r
        r += step

@app.route("/")
def home():
    return render_template("index.html", form_data={}, reinforcement_nums=[], reinforcement_diameters=[], reinforcement_covers=[])

@app.route("/calculate", methods=["POST"])
def calculate():
    form_data = request.form.to_dict()
    additional_loads = []
    load_desc_list = request.form.getlist("load_desc[]")
    load_value_list = request.form.getlist("load_value[]")
    load_type_list = request.form.getlist("load_type[]")
    load_distribution_list = request.form.getlist("load_distribution[]")
    load_material_list = request.form.getlist("load_material[]")
    
    for desc, value, ltype, distr, mat in zip(load_desc_list, load_value_list, load_type_list, load_distribution_list, load_material_list):
        if value.strip():
            additional_loads.append({
                "description": desc,
                "value": get_float(value),
                "type": ltype.lower(),
                "load_distribution": distr.lower(),
                "load_material": mat.lower()
            })
    
    reinforcement_nums = request.form.getlist("reinforcement_num[]")
    reinforcement_diameters = request.form.getlist("reinforcement_diameter[]")
    reinforcement_covers = request.form.getlist("reinforcement_cover[]")
    
    form_data["load_desc[]"] = load_desc_list
    form_data["load_value[]"] = load_value_list
    form_data["load_type[]"] = load_type_list
    form_data["load_distribution[]"] = load_distribution_list
    form_data["load_material[]"] = load_material_list

    result = calculate_beam_capacity(form_data, additional_loads)
    result["Additional Loads"] = additional_loads
    return render_template("index.html", result=result, form_data=form_data,
                           reinforcement_nums=reinforcement_nums,
                           reinforcement_diameters=reinforcement_diameters,
                           reinforcement_covers=reinforcement_covers)

@app.route("/download-pdf", methods=["POST"])
def download_pdf():
    form_data = request.form.to_dict()
    additional_loads = []
    load_desc_list = request.form.getlist("load_desc[]")
    load_value_list = request.form.getlist("load_value[]")
    load_type_list = request.form.getlist("load_type[]")
    load_distribution_list = request.form.getlist("load_distribution[]")
    load_material_list = request.form.getlist("load_material[]")
    
    for desc, value, ltype, distr, mat in zip(load_desc_list, load_value_list, load_type_list, load_distribution_list, load_material_list):
        if value.strip():
            additional_loads.append({
                "description": desc,
                "value": get_float(value),
                "type": ltype.lower(),
                "load_distribution": distr.lower(),
                "load_material": mat.lower()
            })
    
    reinforcement_nums = request.form.getlist("reinforcement_num[]")
    reinforcement_diameters = request.form.getlist("reinforcement_diameter[]")
    reinforcement_covers = request.form.getlist("reinforcement_cover[]")
    
    form_data["load_desc[]"] = load_desc_list
    form_data["load_value[]"] = load_value_list
    form_data["load_type[]"] = load_type_list
    form_data["load_distribution[]"] = load_distribution_list
    form_data["load_material[]"] = load_material_list

    result = calculate_beam_capacity(form_data, additional_loads)
    result["Additional Loads"] = additional_loads

    rendered = render_template("breakdown.html", result=result, form_data=form_data,
                               reinforcement_nums=reinforcement_nums,
                               reinforcement_diameters=reinforcement_diameters,
                               reinforcement_covers=reinforcement_covers)
    pdf = HTML(string=rendered).write_pdf()
    response = make_response(pdf)
    response.headers["Content-Type"] = "application/pdf"
    response.headers["Content-Disposition"] = "attachment; filename=calculation_breakdown.pdf"
    return response

if __name__ == "__main__":
    app.run(debug=True)

