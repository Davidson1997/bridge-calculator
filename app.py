from flask import Flask, render_template, request, jsonify
from bridge_capacity import calculate_bridge_capacity

app = Flask(__name__)

@app.route('/')
def home():
    return render_template("./index.html")  # Load the input page

@app.route('/calculate', methods=['POST'])
def calculate():
    try:
        # Get form data
        bridge_type = request.form.get("bridge_type")
        span_length = float(request.form.get("span_length"))
        material = request.form.get("material")
        beam_section = request.form.get("beam_section")
        applied_loads = {
            "traffic": float(request.form.get("traffic")),
            "wind": float(request.form.get("wind"))
        }
        safety_factors = {
            "steel": 1.05,
            "concrete": 1.3
        }

        # Run calculations
        result = calculate_bridge_capacity(
            bridge_type, span_length, material, beam_section, applied_loads, safety_factors
        )

        return render_template("index.html", result=result)  # Show results on the page

    except Exception as e:
        return f"Error: {str(e)}"

if __name__ == '__main__':
    app.run(debug=True)

