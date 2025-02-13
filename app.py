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
    Note: Shear capacity is converted to kN.
    """
    fy = 275 if steel_grade == "S275" else 355
    if flange_width <= 0 or flange_thickness <= 0 or web_thickness <= 0 or beam_depth <= 0:
        return 0, 0
    # Plastic section modulus [m³]
    Z_plastic = (flange_width * flange_thickness * (beam_depth - flange_thickness) +
                 (web_thickness * (beam_depth - 2 * flange_thickness) ** 2) / 4) / 1e6
    moment_capacity = fy * Z_plastic / condition_factor  # kNm
    shear_capacity = (fy * web_thickness * beam_depth / (1.73 * condition_factor)) / 1000  # Convert N to kN
    return moment_capacity, shear_capacity

def calculate_concrete_capacity(concrete_grade, beam_width, effective_depth, rebar_size=0, rebar_spacing=0):
    """
    Calculates moment and shear capacity for a concrete beam using simplified design formulas.
    (This version uses only the available inputs from the form.)
    """
    # Example: Use 32 for C32/40 and 40 for C40/50
    fck = 32 if concrete_grade == "C32/40" else 40
    moment_capacity = 0.156 * fck * beam_width * effective_depth ** 2 / 1e6  # kNm
    shear_capacity = 0.6 * fck * beam_width * effective_depth / 1e3  # kN
    return moment_capacity, shear_capacity

def calculate_applied_loads(span_length, loading_type, additional_loads):
    """
    Calculates the applied moment and shear from default load cases (HA/HB) plus any additional loads.
    """
    applied_moment = 0
    applied_shear = 0
    
    # Default load values based on loading type (values in kN/m and kN)
    if loading_type == "HA":
        udl = 30   # kN/m
        point_load = 120  # kN
    elif loading_type == "HB":
        udl = 45
        point_load = 180
    else:
        udl = 0
        point_load = 0

    # Contributions from default loads:
    applied_moment += (udl * span_length ** 2) / 8 + (point_load * span_length) / 4
    applied_shear += (udl * span_length) / 2 + point_load / 2
    logging.debug("Default loads: UDL=%s kN/m, Point Load=%s kN", udl, point_load)
    
    # Process additional loads:
    for load in additional_loads:
        load_value = load.get("value", 0)
        distribution = load.get("distribution", "").lower()
        description = load.get("description", "Additional Load")
        if distribution == "udl":
            applied_moment += (load_value * span_length ** 2) / 8
            applied_shear += (load_value * span_length) / 2
            logging.debug("Added UDL: %s (%s kN/m)", description, load_value)
        elif distribution == "point":
            applied_moment += (load_value * span_length) / 4
            applied_shear += load_value / 2
            logging.debug("Added Point Load: %s (%s kN)", description, load_value)
    return applied_moment, applied_shear

def calculate_beam_capacity(form_data, loads):
    """
    Reads input parameters, calculates beam capacities (adjusted for effective member length),
    applied loads, and determines the utilisation.
    """
    material = form_data.get("material")
    condition_factor = get_float(form_data.get("condition_factor"), 1.0)
    span_length = get_float(form_data.get("span_length"))
    # New input for effective member length (if not provided, default to span length)
    effective_member_length = get_float(form_data.get("effective_member_length"), span_length)
    loading_type = form_data.get("loading_type")
    
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

    # Apply effective length reduction on moment capacity (e.g., lateral-torsional buckling effects)
    reduction_factor = 1.0
    if effective_member_length > span_length:
        reduction_factor = span_length / effective_member_length
        moment_capacity = moment_capacity * reduction_factor

    applied_moment, applied_shear = calculate_applied_loads(span_length, loading_type, loads)
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
        "loading_type": loading_type,
        "Additional Loads": loads,
        "Condition Factor": condition_factor
    }
    logging.debug("Calculation result: %s", result)
    return result

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/calculate", methods=["POST"])
def calculate():
    # Get all form fields as a dictionary
    form_data = request.form.to_dict()
    
    # Process additional loads from table rows
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
