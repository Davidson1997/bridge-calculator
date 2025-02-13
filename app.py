from flask import Flask, render_template, request
import math

app = Flask(__name__)

# Define safety factors (BD 21/01)
PARTIAL_FACTORS = {
    "dead": 1.1,      # γfL for dead load
    "super": 1.3,     # γfL for superimposed load
    "live": 1.5,      # γfL for live load
    "steel": 1.05,    # γm for steel
    "concrete": 1.3   # γm for concrete
}

# Condition factor based on deterioration level (Fc)
CONDITION_FACTORS = {
    "new": 1.0,
    "good": 0.9,
    "fair": 0.8,
    "poor": 0.7
}

def get_float(value, default=0.0):
    """Convert input to float safely, defaulting to 0.0 if empty or None."""
    try:
        return float(value.strip()) if value and isinstance(value, str) else default
    except ValueError:
        return default

def calculate_bridge_capacity(data):
    """Performs bridge capacity calculations per BD 21/01."""
    results = {}
    
    # Material selection
    material = data.get("material")
    span_length = get_float(data.get("span_length"))
    loading_type = data.get("loading_type")
    condition = data.get("condition", "new")
    Fc = CONDITION_FACTORS.get(condition, 1.0)

    # Load Inputs
    loads = []
    load_desc_list = data.getlist("load_desc[]")
    load_value_list = data.getlist("load_value[]")
    load_type_list = data.getlist("load_type[]")

    for desc, value, load_type in zip(load_desc_list, load_value_list, load_type_list):
        if value.strip():
            loads.append({"description": desc, "value": get_float(value), "type": load_type})

    moment_capacity, shear_capacity, applied_moment, applied_shear = 0, 0, 0, 0

    if material == "Steel":
        fy = 275 if "S275" in data.get("steel_grade", "") else 355  # Steel strength
        flange_width = get_float(data.get("flange_width"))
        flange_thickness = get_float(data.get("flange_thickness"))
        web_thickness = get_float(data.get("web_thickness"))
        beam_depth = get_float(data.get("beam_depth"))

        if flange_width and flange_thickness and web_thickness and beam_depth:
            Z_plastic = (flange_width * flange_thickness * (beam_depth - flange_thickness) +
                         (web_thickness * (beam_depth - 2 * flange_thickness) ** 2) / 4) / 1e6
            moment_capacity = (fy * Z_plastic / PARTIAL_FACTORS["steel"]) * Fc
            shear_capacity = (fy * web_thickness * beam_depth / (1.73 * PARTIAL_FACTORS["steel"])) * Fc

    elif material == "Concrete":
        fck = 32 if "C32/40" in data.get("concrete_grade", "") else 40
        beam_width = get_float(data.get("beam_width"))
        effective_depth = get_float(data.get("effective_depth"))
        rebar_size = get_float(data.get("rebar_size"))
        rebar_spacing = get_float(data.get("rebar_spacing"))

        if beam_width and effective_depth:
            moment_capacity = (0.156 * fck * beam_width * effective_depth ** 2 / 1e6) * Fc
            shear_capacity = (0.6 * fck * beam_width * effective_depth / 1e3) * Fc

    # Apply BD 21/01 HA & HB Loading
    if loading_type == "HA":
        applied_moment = 0.4 * span_length ** 2
        applied_shear = 0.6 * span_length
    elif loading_type == "HB":
        applied_moment = 0.6 * span_length ** 2
        applied_shear = 0.8 * span_length

    # Apply additional loads
    for load in loads:
        factor = PARTIAL_FACTORS[load["type"]]
        applied_moment += (load["value"] * span_length ** 2 / 8) * factor
        applied_shear += (load["value"] * span_length / 2) * factor

    # Utilisation and pass/fail check
    utilisation = applied_moment / moment_capacity if moment_capacity else 0
    pass_fail = "Pass" if moment_capacity > applied_moment and shear_capacity > applied_shear else "Fail"

    # Store results
    results["Moment Capacity (kNm)"] = round(moment_capacity, 2)
    results["Shear Capacity (kN)"] = round(shear_capacity, 2)
    results["Applied Moment (ULS) (kNm)"] = round(applied_moment, 2)
    results["Applied Shear (kN)"] = round(applied_shear, 2)
    results["Utilisation Ratio"] = round(utilisation, 3)
    results["Pass/Fail"] = pass_fail

    return results

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/calculate", methods=["POST"])
def calculate():
    data = request.form
    results = calculate_bridge_capacity(data)
    return render_template("index.html", result=results)

if __name__ == "__main__":
    app.run(debug=True)
