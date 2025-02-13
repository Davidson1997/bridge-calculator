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
    Calculates moment and shear capacity for a steel beam using a simplified plastic section modulus.
    Applies BD21/01 reduction factors.
    Note: Shear capacity is converted to kN.
    """
    fy = 275 if steel_grade == "S275" else 355
    if flange_width <= 0 or flange_thickness <= 0 or web_thickness <= 0 or beam_depth <= 0:
        return 0, 0
    # Plastic section modulus [m³]
    Z_plastic = (flange_width * flange_thickness * (beam_depth - flange_thickness) +
                 (web_thickness * (beam_depth - 2 * flange_thickness) ** 2) / 4) / 1e6
    moment_capacity = fy * Z_plastic / condition_factor  # kNm
    shear_capacity = (fy * web_thickness * beam_depth / (1.73 * condition_factor)) / 1000  # kN

    # Apply BD21/01 factors (example values; adjust as needed)
    BD21_moment_factor = 0.9
    BD21_shear_factor = 0.95
    moment_capacity *= BD21_moment_factor
    shear_capacity *= BD21_shear_factor

    return moment_capacity, shear_capacity

def calculate_concrete_capacity(concrete_grade, beam_width, effective_depth, rebar_size=0, rebar_spacing=0):
    """
    Calculates moment and shear capacity for a concrete beam using simplified design formulas.
    Applies BD37/01 factors.
    """
    fck = 32 if concrete_grade == "C32/40" else 40
    moment_capacity = 0.156 * fck * beam_width * effective_depth ** 2 / 1e6  # kNm
    shear_capacity = 0.6 * fck * beam_width * effective_depth / 1e3  # kN

    # Apply BD37/01 factors (example values; adjust as needed)
    BD37_moment_factor = 0.95
    BD37_shear_factor = 1.0
    moment_capacity *= BD37_moment_factor
    shear_capacity *= BD37_shear_factor

    return moment_capacity, shear_capacity

def calculate_applied_loads(span_length, loading_type, additional_loads, loaded_width=None, access_factor=None, lane_width=None):
    """
    Calculates the applied moment and shear from the default load case plus any additional loads.
    
    For HA loading:
      - Base UDL = 230*(1/span_length)^0.67  [kN/m]
      - Effective UDL = ((Base UDL × 0.76) / (3.65/2.5)) × (Loaded Carriageway Width/2.5) × Access Factor
      - HA KEL = ((82 × 0.76) / (3.65/2.5)) × (Loaded Carriageway Width/2.5) × Access Factor   (82 kN is constant)
      
      Then:
          Applied Moment = (Effective UDL × L²)/8 + (HA KEL × L)/4
          Applied Shear  = (Effective UDL × L)/2 + (HA KEL)/2
          
    For HB loading, fixed values are used.
    """
    if loading_type == "HA":
        # Calculate base UDL from span:
        base_udl = 230 * (1 / span_length)**0.67  # kN/m; this will be ~43.7 kN/m for a span of 11.9 m
        if loaded_width is None or loaded_width <= 0:
            loaded_width = 3.65  # default standard width
        if access_factor is None:
            access_factor = 1.3  # default to company access
        effective_udl = ((base_udl * 0.76) / (3.65 / 2.5)) * (loaded_width / 2.5) * access_factor

        # HA KEL is a constant 82 kN (base) scaled by the same factors:
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
    """
    Reads input parameters, calculates the beam's capacity (with effective length reductions),
    and computes the applied loads using the effective UDL and HA KEL formulas.
    """
    material = form_data.get("material")
    condition_factor = get_float(form_data.get("condition_factor"), 1.0)
    span_length = get_float(form_data.get("span_length"))
    effective_member_length = get_float(form_data.get("effective_member_length"), span_length)
    loading_type = form_data.get("loading_type")
    
    # Retrieve inputs for loaded carriageway and access type:
    loaded_width = get_float(form_data.get("loaded_width"), 3.65)
    access_str = form_data.get("access_type", "Company")
    access_factor = 1.5 if access_str.lower() == "public" else 1.3
    # (For HA, lane width is no longer used for the base value; HA KEL remains constant at 82 kN)
    
    # Capacity calculation based on material:
    if material == "Steel":
        steel_grade = form_data.get("steel_grade")
        flange_width = get_float(form_data.get("flange_width"))
        flange_thickness = get_float(form_data.get("flange_thickness"))
        web_thickness = get_float(form_data.get("web_thickness"))
        beam_depth = get_float(form_data.get("beam_depth"))
        moment_capacity, shear_capacity = calculate_steel_capacity(
            steel_grade, flange_width, flange_thickness, web_thickness, beam_depth, condition_factor)
    elif material == "Concrete":
        concrete_grade = form_data.get("concrete_grade")
        beam_width = get_float(form_data.get("beam_width"))
        effective_depth = get_float(form_data.get("effective_depth"))
        moment_capacity, shear_capacity = calculate_concrete_capacity(
            concrete_grade, beam_width, effective_depth)
    else:
        moment_capacity, shear_capacity = 0, 0

    # Apply effective length reduction if effective_member_length > span_length:
    reduction_factor = 1.0
    if effective_member_length > span_length:
        reduction_factor = span_length / effective_member_length
        moment_capacity *= reduction_factor

    applied_moment, applied_shear, default_loads = calculate_applied_loads(
        span_length, loading_type, loads, loaded_width, access_factor)
    utilisation_ratio = applied_moment / moment_capacity if moment_capacity > 0 else float('inf')
    pass_fail = "Pass" if moment_capacity >= applied_moment and shear_capacity >= applied_shear else "Fail"

    result = {
        "Span Length (m)": span_length,
        "Effective Member Length (m)": effective_member_length,
        "Reduction Factor": round(reduction_factor, 3),
        "Moment Capacity (kNm)": round(moment_capacity, 2),
        "Shear Capacity (kN)": round(shear_capacity, 2),
        "Applied Moment (ULS) (kNm)": round(applied_moment, 2),
        "Applied Shear (ULS) (kN)": round(applied_shear, 2),
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
    return render_template("index.html")

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
    return render_template("index.html", result=result)

if __name__ == "__main__":
    app.run(debug=True)
