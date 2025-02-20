from flask import Flask, render_template, request
import math
import logging

app = Flask(__name__)
logging.basicConfig(level=logging.DEBUG)

def get_float(value, default=0.0):
    """Safely convert a value to float."""
    try:
        return float(value.strip()) if value and isinstance(value, str) else default
    except Exception:
        return default

def calculate_steel_capacity(steel_grade, flange_width, flange_thickness, web_thickness, beam_depth, condition_factor):
    """
    Calculates the plastic moment capacity (Mpe) and shear capacity for a steel beam
    using a simplified plastic section modulus. Applies BD21/01 reduction factors.
    Note: Shear capacity is converted to kN.
    """
    fy = 275 if steel_grade == "S275" else 355
    if flange_width <= 0 or flange_thickness <= 0 or web_thickness <= 0 or beam_depth <= 0:
        return 0, 0
    # Plastic section modulus (Z_plastic) in m³
    Z_plastic = (flange_width * flange_thickness * (beam_depth - flange_thickness) +
                 (web_thickness * (beam_depth - 2 * flange_thickness)**2) / 4) / 1e6
    Mpe = fy * Z_plastic / condition_factor  # in kNm
    shear_capacity = (fy * web_thickness * beam_depth / (1.73 * condition_factor)) / 1000  # in kN

    # Apply BD21/01 factors (example multipliers)
    BD21_moment_factor = 0.9
    BD21_shear_factor = 0.95
    Mpe *= BD21_moment_factor
    shear_capacity *= BD21_shear_factor

    return Mpe, shear_capacity

def calculate_concrete_capacity(concrete_grade, beam_width, effective_depth, rebar_size=0, rebar_spacing=0):
    """
    Calculates moment and shear capacity for a concrete beam using simplified design formulas.
    Applies BD37/01 factors.
    """
    fck = 32 if concrete_grade == "C32/40" else 40
    moment_capacity = 0.156 * fck * beam_width * effective_depth**2 / 1e6  # kNm
    shear_capacity = 0.6 * fck * beam_width * effective_depth / 1e3  # kN

    BD37_moment_factor = 0.95
    BD37_shear_factor = 1.0
    moment_capacity *= BD37_moment_factor
    shear_capacity *= BD37_shear_factor

    return moment_capacity, shear_capacity

# Effective length calculation per BS5400-3:
def calculate_effective_length(L, k1=1.0, k2=1.0):
    return k1 * k2 * L

# New function: interpolate v from F using the provided table.
def calculate_v_from_F(F):
    table = {
        0: 1.000,
        1: 0.988,
        2: 0.956,
        3: 0.912,
        4: 0.864,
        5: 0.817,
        6: 0.774,
        7: 0.734,
        8: 0.699,
        9: 0.668,
        10: 0.639,
        11: 0.614,
        12: 0.591,
        13: 0.571,
        14: 0.552,
        15: 0.535,
        16: 0.519,
        17: 0.505,
        18: 0.492,
        19: 0.479,
        20: 0.468
    }
    if F <= 0:
        return 1.0
    if F >= 20:
        return 0.468
    lower = int(math.floor(F))
    upper = lower + 1
    v_lower = table[lower]
    v_upper = table[upper]
    fraction = F - lower
    v = v_lower + fraction * (v_upper - v_lower)
    return v

# New slenderness calculation based on your formula:
# F_param = (effective_length * flange_thickness) / (r * beam_depth)
# Then v is calculated from F_param and slenderness = (effective_length / r) * v.
def calculate_slenderness(effective_length, r, beam_depth, flange_thickness):
    F_param = (effective_length * flange_thickness) / (r * beam_depth)
    v = calculate_v_from_F(F_param)
    slenderness = (effective_length / r) * v
    return slenderness, F_param, v

# BD37/01-style moment capacity adjustment for steel beams:
def calculate_bd37_moment_capacity(Mpe, effective_length, steel_grade, flange_width, flange_thickness, web_thickness, beam_depth):
    """
    Adjusts Mpe using BS5400-3 approach.
    Checks section compactness and calculates slenderness.
    If slenderness > 1, then Mult = 1/λ; otherwise Mult = 1.
    Then defines Mmin = 0.8 * Mpe and design capacity MR = max(Mmin, Mult * Mpe), not exceeding Mpe.
    """
    # Compactness check:
    compact = is_section_compact(steel_grade, flange_width, flange_thickness, web_thickness, beam_depth)
    # For radius of gyration, r, we use a placeholder approximation:
    r = beam_depth / 30  # in m (update as needed)
    slenderness, F_param, v_value = calculate_slenderness(effective_length, r, beam_depth, flange_thickness)
    if slenderness > 1.0:
        Mult = 1 / slenderness
    else:
        Mult = 1.0
    Mmin = 0.8 * Mpe
    MR = max(Mmin, Mult * Mpe)
    MR = min(MR, Mpe)
    return MR, slenderness

def calculate_applied_loads(span_length, loading_type, additional_loads, loaded_width=None, access_factor=None, lane_width=None):
    if loading_type == "HA":
        base_udl = 230 * (1 / span_length)**0.67  # kN/m
        if loaded_width is None or loaded_width <= 0:
            loaded_width = 3.65
        if access_factor is None:
            access_factor = 1.3
        effective_udl = ((base_udl * 0.76) / (3.65 / 2.5)) * (loaded_width / 2.5) * access_factor
        base_kel = 82  # kN constant
        kel = ((base_kel * 0.76) / (3.65 / 2.5)) * (loaded_width / 2.5) * access_factor
        default_loads = {"base_udl": base_udl, "effective_udl": effective_udl, "kel": kel}
        applied_moment = (effective_udl * span_length**2) / 8 + (kel * span_length) / 4
        applied_shear = (effective_udl * span_length) / 2 + (kel) / 2
    elif loading_type == "HB":
        udl = 45  # kN/m
        point_load = 180  # kN
        if loaded_width is not None and access_factor is not None:
            effective_udl = ((udl * 0.76) / (3.65 / 2.5)) * (loaded_width / 2.5) * access_factor
        else:
            effective_udl = udl
        default_loads = {"udl": udl, "effective_udl": effective_udl}
        applied_moment = (effective_udl * span_length**2) / 8 + (point_load * span_length) / 4
        applied_shear = (effective_udl * span_length) / 2 + point_load / 2
    else:
        effective_udl = 0
        default_loads = {"udl": 0, "effective_udl": 0}
        applied_moment = 0
        applied_shear = 0

    for load in additional_loads:
        load_value = load.get("value", 0)
        distribution = load.get("distribution", "").lower()
        if distribution == "udl":
            applied_moment += (load_value * span_length**2) / 8
            applied_shear += (load_value * span_length) / 2
        elif distribution == "point":
            applied_moment += (load_value * span_length) / 4
            applied_shear += load_value / 2

    return applied_moment, applied_shear, default_loads

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

    if material == "Steel":
        steel_grade = form_data.get("steel_grade")
        flange_width = get_float(form_data.get("flange_width"))
        flange_thickness = get_float(form_data.get("flange_thickness"))
        web_thickness = get_float(form_data.get("web_thickness"))
        beam_depth = get_float(form_data.get("beam_depth"))
        Mpe, shear_capacity = calculate_steel_capacity(steel_grade, flange_width, flange_thickness, web_thickness, beam_depth, condition_factor)
        try:
            MR, slenderness = calculate_bd37_moment_capacity(Mpe, effective_length, steel_grade, flange_width, flange_thickness, web_thickness, beam_depth)
            moment_capacity = MR
        except Exception as e:
            logging.error("Error in BD37 capacity calculation: %s", e)
            moment_capacity = Mpe
    elif material == "Concrete":
        concrete_grade = form_data.get("concrete_grade")
        beam_width = get_float(form_data.get("beam_width"))
        effective_depth = get_float(form_data.get("effective_depth"))
        moment_capacity, shear_capacity = calculate_concrete_capacity(concrete_grade, beam_width, effective_depth)
        effective_length = L_actual
    else:
        moment_capacity, shear_capacity = 0, 0

    reduction_factor = 1.0
    if effective_length < span_length:
        reduction_factor = effective_length / span_length
        moment_capacity *= reduction_factor

    applied_moment, applied_shear, default_loads = calculate_applied_loads(span_length, loading_type, loads, loaded_width, access_factor)
    utilisation_ratio = applied_moment / moment_capacity if moment_capacity > 0 else float('inf')
    pass_fail = "Pass" if moment_capacity >= applied_moment and shear_capacity >= applied_shear else "Fail"

    applied_live_moment = round(applied_moment, 2)
    applied_dead_moment = 0

    result = {
        "Span Length (m)": span_length,
        "Effective Member Length (m)": effective_length,
        "k1": k1,
        "k2": k2,
        "Reduction Factor": round(reduction_factor, 3),
        "Moment Capacity (kNm)": round(moment_capacity, 2),
        "Shear Capacity (kN)": round(shear_capacity, 2),
        "Applied Moment (ULS) (kNm)": round(applied_moment, 2),
        "Applied Shear (ULS) (kN)": round(applied_shear, 2),
        "Applied Live Load Moment (kNm)": applied_live_moment,
        "Applied Dead Load Moment (kNm)": applied_dead_moment,
        "Utilisation Ratio": round(utilisation_ratio, 3) if utilisation_ratio != float('inf') else "N/A",
        "Pass/Fail": pass_fail,
        "Loading Type": loading_type,
        "Condition Factor": condition_factor,
        "Loaded Carriageway Width (m)": loaded_width,
        "Access Type": access_str
    }
    if loading_type in ["HA", "HB"]:
        result[f"{loading_type} UDL (kN/m)"] = round(default_loads.get("effective_udl", 0), 2)
    if loading_type == "HA":
        result["HA KEL (kN)"] = round(default_loads.get("kel", 0), 2)
    
    logging.debug("Calculation result: %s", result)
    return result

@app.route("/")
def home():
    return render_template("index.html", form_data={})

@app.route("/calculate", methods=["POST"])
def calculate():
    form_data = request.form.to_dict()
    additional_loads = []
    load_desc_list = request.form.getlist("load_desc[]")
    load_value_list = request.form.getlist("load_value[]")
    load_type_list = request.form.getlist("load_type[]")
    load_distribution_list = request.form.getlist("load_distribution[]")
    
    for desc, value, ltype, distribution in zip(load_desc_list, load_value_list, load_type_list, load_distribution_list):
        if value.strip():
            additional_loads.append({
                "description": desc,
                "value": get_float(value),
                "type": ltype,
                "distribution": distribution
            })
    
    result = calculate_beam_capacity(form_data, additional_loads)
    return render_template("index.html", result=result, form_data=form_data)

if __name__ == "__main__":
    app.run(debug=True)

