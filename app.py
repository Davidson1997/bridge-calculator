
  from flask import Flask, render_template, request, jsonify
import math

app = Flask(__name__)

def calculate_bridge_capacity(material, span_length, loading_type, flange_width, flange_thickness, web_thickness, beam_depth, beam_width, effective_depth, rebar_size, rebar_spacing, condition_factor):
    results = {}
    
    if material == "Steel":
        fy = 275 if "S275" else 355  # Yield strength in MPa
        Z_plastic = (flange_width * flange_thickness * (beam_depth - flange_thickness) + (web_thickness * (beam_depth - 2 * flange_thickness) ** 2) / 4) / 1e6  # Plastic modulus (m^3)
        moment_capacity = fy * Z_plastic / condition_factor
        shear_capacity = fy * web_thickness * beam_depth / (1.73 * condition_factor)  # Shear based on web thickness
    
    elif material == "Concrete":
        fck = 32 if "C32/40" else 40  # Concrete strength in MPa
        fyk = 500  # Reinforcement steel strength
        As = (1000 / rebar_spacing) * (math.pi * (rebar_size / 2) ** 2)  # Reinforcement area per m width
        moment_capacity = 0.156 * fck * beam_width * effective_depth ** 2 / 1e6
        shear_capacity = 0.6 * fck * beam_width * effective_depth / 1e3
    
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
    results = calculate_bridge_capacity(
        data.get("material"),
        float(data.get("span_length")),
        data.get("loading_type"),
        float(data.get("flange_width", 0)),
        float(data.get("flange_thickness", 0)),
        float(data.get("web_thickness", 0)),
        float(data.get("beam_depth", 0)),
        float(data.get("beam_width", 0)),
        float(data.get("effective_depth", 0)),
        float(data.get("rebar_size", 0)),
        float(data.get("rebar_spacing", 0)),
        float(data.get("condition_factor", 1))
    )
    return render_template("index.html", result=results)

if __name__ == "__main__":
    app.run(debug=True)