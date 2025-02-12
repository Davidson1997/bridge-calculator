from flask import Flask, render_template, request, jsonify
import math

app = Flask(__name__, template_folder="templates")

# Material Properties (Eurocode Compliant)
MATERIAL_PROPERTIES = {
    "Steel": {
        "S275": {"fy": 275, "E": 210e3},
        "S355": {"fy": 355, "E": 210e3}
    },
    "Concrete": {
        "C32/40": {"fck": 32, "E": 30e3},
        "C40/50": {"fck": 40, "E": 33e3}
    },
    "Timber": {
        "C24": {"fm": 24, "E": 11e3},
        "C30": {"fm": 30, "E": 12e3}
    }
}

# HA and HB Loading Factors (BS 5400 / BD 37/01)
HA_LOADING = {
    "udl": 30,  # kN/m
    "kel_factor": 1.2  # Enhancement factor
}
HB_LOADING = {
    "axle_load": 180,  # kN per axle
    "spacing": 1.2  # Axle spacing in meters
}

def calculate_beam_capacity(material, grade, section, span, condition_factor, loading_type, rebar=None):
    properties = MATERIAL_PROPERTIES[material][grade]
    
    if material == "Steel":
        fy = properties["fy"]
        moment_capacity = (fy * section["depth"] * section["width"]**2) / 6  # Elastic capacity
        shear_capacity = (fy * section["width"] * section["depth"]) / 3
    
    elif material == "Concrete":
        fck = properties["fck"]
        As = (math.pi * (rebar["size"] ** 2) / 4) * (1000 / rebar["spacing"])  # Reinforcement area
        moment_capacity = (0.85 * fck * As * section["depth"] * 0.9) / 1.5
        shear_capacity = (0.6 * fck * section["width"] * section["depth"]) / 1.5
    
    elif material == "Timber":
        fm = properties["fm"]
        moment_capacity = (fm * section["width"] * section["depth"] ** 2) / 6 * condition_factor
        shear_capacity = (fm * section["width"] * section["depth"]) / 3 * condition_factor
    
    # Apply HA or HB Loading
    if loading_type == "HA":
        applied_moment = (HA_LOADING["udl"] * span ** 2) / 8 * HA_LOADING["kel_factor"]
        applied_shear = (HA_LOADING["udl"] * span) / 2 * HA_LOADING["kel_factor"]
    else:  # HB Loading
        applied_moment = (HB_LOADING["axle_load"] * span / HB_LOADING["spacing"]) * 0.9
        applied_shear = HB_LOADING["axle_load"] * 0.8
    
    # Check Pass/Fail
    pass_fail = "Pass" if moment_capacity > applied_moment and shear_capacity > applied_shear else "Fail"
    
    return {
        "moment_capacity_kNm": round(moment_capacity, 2),
        "shear_capacity_kN": round(shear_capacity, 2),
        "applied_moment_kNm": round(applied_moment, 2),
        "applied_shear_kN": round(applied_shear, 2),
        "pass_fail": pass_fail
    }


@app.route('/')
def home():
    return render_template("index.html")

@app.route('/calculate', methods=['POST'])
def calculate():
    try:
        data = request.form
        material = data["material"]
        grade = data.get("steel_grade") or data.get("concrete_grade") or data.get("timber_grade")
        span_length = float(data["span_length"])
        condition_factor = float(data["condition_factor"])
        loading_type = data["loading_type"]

        section = {
            "width": float(data["beam_section"].split("x")[0]),
            "depth": float(data["beam_section"].split("x")[1])
        }

        rebar = None
        if material == "Concrete":
            rebar = {
                "size": float(data["rebar_size"]),
                "spacing": float(data["rebar_spacing"])
            }

        result = calculate_beam_capacity(material, grade, section, span_length, condition_factor, loading_type, rebar)
        return render_template("index.html", result=result)
    
    except Exception as e:
        return f"Error: {str(e)}"

if __name__ == '__main__':
    app.run(debug=True)

