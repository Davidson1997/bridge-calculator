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

    # Apply HA & HB Loading (FIXED)
    if loading_type == "HA":
        udl = 30  # Example UDL from BD 21/01 (kN/m)
        point_load = 120  # Example knife-edge load (kN)
    elif loading_type == "HB":
        udl = 45
        point_load = 180

    applied_moment += (udl * span_length ** 2) / 8  # UDL effect
    applied_moment += (point_load * span_length) / 4  # Point load effect

    applied_shear += (udl * span_length) / 2  # Shear effect
    applied_shear += point_load / 2  # Shear from point load

    # Process Additional Loads (FIXED to Include UDL & Point Load)
    print("--- DEBUG: Processing Additional Loads ---")
    for load in loads:
        load_value = load["value"]
        load_type = load["type"]
        load_distribution = load["distribution"]

        if load_distribution == "udl":  # UDL (kN/m)
            applied_moment += (load_value * span_length ** 2) / 8
            applied_shear += (load_value * span_length) / 2
            print(f"Added UDL: {load['description']} ({load_value} kN/m)")
        elif load_distribution == "point":  # Point Load (kN)
            applied_moment += (load_value * span_length) / 4
            applied_shear += load_value / 2
            print(f"Added Point Load: {load['description']} ({load_value} kN)")

    # Final Checks
    utilisation_ratio = applied_moment / moment_capacity if moment_capacity > 0 else 0
    pass_fail = "Pass" if moment_capacity > applied_moment and shear_capacity > applied_shear else "Fail"

    # Debugging Output
    print("--- DEBUG: Calculation Breakdown ---")
    print("Span Length:", span_length)
    print("Applied Moment (ULS):", applied_moment)
    print("Applied Shear (ULS):", applied_shear)
    print("Shear Capacity:", shear_capacity)
    print("Moment Capacity:", moment_capacity)

    results["Moment Capacity (kNm)"] = round(moment_capacity, 2)
    results["Shear Capacity (kN)"] = round(shear_capacity, 2)
    results["Applied Moment (ULS) (kNm)"] = round(applied_moment, 2)
    results["Applied Shear (ULS) (kN)"] = round(applied_shear, 2)
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
    load_distribution_list = data.getlist("load_distribution[]")

    if load_desc_list and load_value_list and load_type_list and load_distribution_list:
        for desc, value, load_type, distribution in zip(load_desc_list, load_value_list, load_type_list, load_distribution_list):
            if value.strip():
                loads.append({"description": desc, "value": get_float(value), "type": load_type, "distribution": distribution})

    print("--- DEBUG: Received Loads ---")
    print(loads)  # Debugging print

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
