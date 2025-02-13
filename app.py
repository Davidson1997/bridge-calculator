from flask import Flask, render_template, request
import math

app = Flask(__name__)

def get_float(value, default=0.0):
    """Convert input to float safely, defaulting to 0.0 if empty or None."""
    try:
        return float(value.strip()) if value and isinstance(value, str) else default
    except ValueError:
        return default

def calculate_bridge_capacity(material, span_length, loading_type, steel_grade, concrete_grade, flange_width, flange_thickness, web_thickness, beam_depth, beam_width, effective_depth, rebar_size, rebar_spacing, condition_factor, loads):
    """Performs bridge capacity calculations for Steel and Concrete with BD 21/01 enhancements."""
    
    # Default Values
    results = {}
    moment_capacity = 0
    shear_capacity = 0
    applied_moment = 0
    applied_shear = 0
    γ_fL = 1.35  # Partial safety factor for loads (per BD 21/01)
    γ_m = 1.1    # Partial safety factor for materials (per BD 21/01)

    # Steel Calculation
    if material == "Steel":
        fy = 275 if steel_grade == "S275" else 355  # Yield Strength (MPa)
        
        if flange_width > 0 and flange_thickness > 0 and web_thickness > 0 and beam_depth > 0:
            Z_plastic = (flange_width * flange_thickness * (beam_depth - flange_thickness) + 
                        (web_thickness * (beam_depth - 2 * flange_thickness) ** 2) / 4) / 1e6  # Plastic modulus in m³
            moment_capacity = fy * Z_plastic / (γ_m * condition_factor)
            shear_capacity = fy * web_thickness * beam_depth / (1.73 * γ_m * condition_factor)

    # Concrete Calculation
    elif material == "Concrete":
        fck = 32 if concrete_grade == "C32/40" else 40  # Concrete Strength (MPa)
        fyk = 500  # Reinforcement Steel Strength (MPa)

        if beam_width > 0 and effective_depth > 0:
            As = (1000 / rebar_spacing) * (math.pi * (rebar_size / 2) ** 2) if rebar_spacing > 0 else 0
            moment_capacity = 0.156 * fck * beam_width * effective_depth ** 2 / (γ_m * 1e6)
            shear_capacity = 0.6 * fck * beam_width * effective_depth / (γ_m * 1e3)

    # HA & HB Load Calculations (BD 21/01)
    if loading_type == "HA":
        applied_moment = γ_fL * (0.4 * span_length ** 2)
        applied_shear = γ_fL * (0.6 * span_length)
    elif loading_type == "HB":
        applied_moment = γ_fL * (0.6 * span_length ** 2)
        applied_shear = γ_fL * (0.8 * span_length)

    # Dynamic Load Amplification (BD 21/01)
    dynamic_factor = 1.2
    applied_moment *= dynamic_factor
    applied_shear *= dynamic_factor

    # Additional Dead/Live Loads
    for load in loads:
        load_value = load["value"]
        if load["type"] == "dead":
            applied_moment += γ_fL * (load_value * span_length ** 2 / 8)
        elif load["type"] == "live":
            applied_moment += γ_fL * (load_value * span_length ** 2 / 12)

    # Utilisation & Pass/Fail Criteria
    utilisation_ratio = applied_moment / moment_capacity if moment_capacity > 0 else 0
    pass_fail = "Pass" if moment_capacity > applied_moment and shear_capacity > applied_shear else "Fail"

    # Results
    results["Moment Capacity (kNm)"] = round(moment_capacity, 2)
    results["Shear Capacity (kN)"] = round(shear_capacity, 2)
    results["Applied Moment (ULS) (kNm)"] = round(applied_moment, 2)
    results["Utilisation Ratio"] = round(utilisation_ratio, 3)
    results["Pass/Fail"] = pass_fail

    return results

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/calculate", methods=["POST"])
def calculate():
    data = request.form
    
    # Capture additional loads
    loads = []
    load_desc_list = data.getlist("load_desc[]")
    load_value_list = data.getlist("load_value[]")
    load_type_list = data.getlist("load_type[]")

    if load_desc_list and load_value_list and load_type_list:
        for desc, value, load_type in zip(load_desc_list, load_value_list, load_type_list):
            if value.strip():  # Ensure it's not empty
                loads.append({"description": desc, "value": get_float(value), "type": load_type})

    results = calculate_bridge_capacity(
        data.get("material"),
        get_float(data.get("span_length")),
        data.get("loading_type"),
        data.get("steel_grade"),
        data.get("concrete_grade"),
        get_float(data.get("flange_width")),
        get_float(data.get("flange_thickness")),
        get_float(data.get("web_thickness")),
        get_float(data.get("beam_depth")),
        get_float(data.get("beam_width")),
        get_float(data.get("effective_depth")),
        get_float(data.get("rebar_size")),
        get_float(data.get("rebar_spacing")),
        get_float(data.get("condition_factor"), 1.0),
        loads
    )

    return render_template("index.html", result=results)

if __name__ == "__main__":
    app.run(debug=True)
