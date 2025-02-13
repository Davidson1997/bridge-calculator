from flask import Flask, render_template, request
import math

app = Flask(__name__)

def get_float(value, default=0.0):
    """Convert input to float safely, defaulting to 0.0 if empty or None."""
    try:
        return float(value.strip()) if value and isinstance(value, str) else default
    except ValueError:
        return default

def calculate_bridge_capacity(material, span_length, loading_type, flange_width, flange_thickness, web_thickness, beam_depth, beam_width, effective_depth, rebar_size, rebar_spacing, condition_factor):
    """Performs bridge capacity calculations for Steel and Concrete."""
    results = {}

    if material == "Steel":
        fy = 275 if "S275" in material else 355  # Yield strength in MPa
        if flange_width > 0 and flange_thickness > 0 and web_thickness > 0 and beam_depth > 0:
            Z_plastic = (flange_width * flange_thickness * (beam_depth - flange_thickness) + 
                         (web_thickness * (beam_depth - 2 * flange_thickness) ** 2) / 4) / 1e6  # Plastic modulus (m^3)
            moment_capacity = fy * Z_plastic / condition_factor
            shear_capacity = fy * web_thickness * beam_depth / (1.73 * condition_factor)  # Shear based on web thickness
        else:
            moment_capacity = 0
            shear_capacity = 0

    elif material == "Concrete":
        fck = 32 if "C32/40" in material else 40  # Concrete strength in MPa
        fyk = 500  # Reinforcement steel strength
        if beam_width > 0 and effective_depth > 0:
            As = (1000 / rebar_spacing) * (math.pi * (rebar_size / 2) ** 2) if rebar_spacing > 0 else 0  # Reinforcement area per m width
            moment_capacity = 0.156 * fck * beam_width * effective_depth ** 2 / 1e6
            shear_capacity = 0.6 * fck * beam_width * effective_depth / 1e3
        else:
            moment_capacity = 0
            shear_capacity = 0
    else:
        moment_capacity = 0
        shear_capacity = 0

    # HA & HB Loading Calculations
    if loading_type == "HA":
        applied_moment = 0.4 * span_length ** 2  # UDL applied load (BS 5400 UDL estimate)
        applied_shear = 0.6 * span_length  # Approximate reaction
    elif loading_type == "HB":
        applied_moment = 0.6 * span_length ** 2  # HB vehicle with point loads
        applied_shear = 0.8 * span_length
    else:
        applied_moment = 0
        applied_shear = 0

    pass_fail = "Pass" if moment_capacity > applied_moment and shear_capacity > applied_shear else "Fail"

    results["moment_capacity_kNm"] = round(moment_capacity, 2)
    results["shear_capacity_kN"] = round(shear_capacity, 2)
    results["applied_moment_kNm"] = round(applied_moment, 2)
    results["applied_shear_kN"] = round(applied_shear, 2)
    results["pass_fail"] = pass_fail

    return results

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/calculate", methods=["POST"])
def calculate():
    data = request.form

    # Log form data to identify errors
    print("Received Data:", data)

    results = calculate_bridge_capacity(
        data.get("material"),
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
        get_float(data.get("condition_factor"), 1.0)
    )

    return render_template("index.html", result=results)

if __name__ == "__main__":
    app.run(debug=True)
