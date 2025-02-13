from flask import Flask, render_template, request
import math

app = Flask(__name__)

def get_float(value, default=0.0):
    """Convert input to float safely, defaulting to 0.0 if empty or None."""
    try:
        return float(value.strip()) if value and isinstance(value, str) else default
    except ValueError:
        return default

def calculate_bridge_capacity(material, steel_grade, concrete_grade, span_length, loading_type, flange_width, flange_thickness, web_thickness, beam_depth, beam_width, effective_depth, rebar_size, rebar_spacing, condition_factor, loads):
    """Performs bridge capacity calculations for Steel and Concrete with additional loads."""
    results = {}
    moment_capacity = 0
    shear_capacity = 0
    applied_moment = 0
    applied_shear = 0

    # Steel Calculation
    if material == "Steel":
        fy = 275 if steel_grade == "S275" else 355
        if flange_width > 0 and flange_thickness > 0 and web_thickness > 0 and beam_depth > 0:
            Z_plastic = (flange_width * flange_thickness * (beam_depth - flange_thickness) + (web_thickness * (beam_depth - 2 * flange_thickness) ** 2) / 4) / 1e6
            moment_capacity = fy * Z_plastic / condition_factor
            shear_capacity = fy * web_thickness * beam_depth / (1.73 * condition_factor)

    # Concrete Calculation
    elif material == "Concrete":
        fck = 32 if concrete_grade == "C32/40" else 40
        fyk = 500
        if beam_width > 0 and effective_depth > 0:
            As = (1000 / rebar_spacing) * (math.pi * (rebar_size / 2) ** 2) if rebar_spacing > 0 else 0
            moment_capacity = 0.156 * fck * beam_width * effective_depth ** 2 / 1e6
            shear_capacity = 0.6 * fck * beam_width * effective_depth / 1e3

    # HA & HB Loading
    if loading_type == "HA":
        applied_moment = 0.4 * span_length ** 2
        applied_shear = 0.6 * span_length
    elif loading_type == "HB":
        applied_moment = 0.6 * span_length ** 2
        applied_shear = 0.8 * span_length

    # Add additional dead/live loads
    for load in loads:
        load_value = load["value"]
        if load["type"] == "dead":
            applied_moment += load_value * span_length ** 2 / 8
        elif load["type"] == "live":
            applied_moment += load_value * span_length ** 2 / 12  # Adjusted factor for live loads

    utilisation_ratio = applied_moment / moment_capacity if moment_capacity > 0 else 0
    pass_fail = "Pass" if moment_capacity > applied_moment and shear_capacity > applied_shear else "Fail"

    # Debugging Output
    print("DEBUG: Span Length =", span_length)
    print("DEBUG: Applied Moment =", applied_moment)
    print("DEBUG: Shear Capacity =", shear_capacity)
    print("DEBUG: Utilisation Ratio =", utilisation_ratio)

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
    loads = []
    load_desc_list = data.getlist("load_desc[]")
    load_value_list = data.getlist("load_value[]")
    load_type_list = data.getlist("load_type[]")
    if load_desc_list and load_value_list and load_type_list:
        for desc, value, load_type in zip(load_desc_list, load_value_list, load_type_list):
            if value.strip():
                loads.append({"description": desc, "value": get_float(value), "type": load_type})

	print("Received loads:", loads)  # Debugging line

    results = calculate_bridge_capacity(
        data.get("material"),
        data.get("steel_grade"),
        data.get("concrete_grade"),
        get_float(data.get("span_length")),
        data.get("loading_type"),
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
