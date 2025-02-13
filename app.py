from flask import Flask, render_template, request
import math

app = Flask(__name__)

def get_float(value, default=0.0):
    try:
        return float(value.strip()) if value and isinstance(value, str) else default
    except ValueError:
        return default

def calculate_bridge_capacity(material, grade, span_length, loading_type, flange_width, flange_thickness, web_thickness, beam_depth, beam_width, effective_depth, condition_factor):
    results = {}

    moment_capacity = 0
    shear_capacity = 0
    applied_moment = 0
    applied_shear = 0

    # **Steel Calculation**
    if material == "Steel":
        fy = 275 if grade == "S275" else 355  
        γm = 1.05  
        if flange_width > 0 and flange_thickness > 0 and web_thickness > 0 and beam_depth > 0:
            Z_plastic = (flange_width * flange_thickness * (beam_depth - flange_thickness) + (web_thickness * (beam_depth - 2 * flange_thickness) ** 2) / 4) / 1e6
            moment_capacity = (fy * Z_plastic) / (γm * condition_factor)
            shear_capacity = (fy * web_thickness * beam_depth) / (1.73 * γm * condition_factor)

    # **Concrete Calculation**
    elif material == "Concrete":
        fck = 32 if grade == "C32/40" else 40  
        γc = 1.5  
        if beam_width > 0 and effective_depth > 0:
            moment_capacity = (0.156 * fck * beam_width * effective_depth ** 2) / (γc * 1e6)
            shear_capacity = (0.6 * fck * beam_width * effective_depth) / (γc * 1e3)

    utilisation_ratio = applied_moment / moment_capacity if moment_capacity > 0 else 0
    results["Pass/Fail"] = "Pass" if moment_capacity > applied_moment and shear_capacity > applied_shear else "Fail"

    return results

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/calculate", methods=["POST"])
def calculate():
    data = request.form
    results = calculate_bridge_capacity(
        data.get("material"),
        data.get("grade"),
        get_float(data.get("span_length")),
        data.get("loading_type"),
        get_float(data.get("flange_width")),
        get_float(data.get("flange_thickness")),
        get_float(data.get("web_thickness")),
        get_float(data.get("beam_depth")),
        get_float(data.get("beam_width")),
        get_float(data.get("effective_depth")),
        get_float(data.get("condition_factor")),
	print(results)  # Debugging - Check if the function outputs correct values

    )
    return render_template("index.html", result=results)

if __name__ == "__main__":
    app.run(debug=True)
