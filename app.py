from flask import Flask, request, jsonify
from bridge_capacity import calculate_bridge_capacity

app = Flask(__name__)

@app.route('/')
def home():
    return "Bridge Capacity Calculator API is Running!"

@app.route('/calculate', methods=['POST'])
def calculate():
    try:
        data = request.get_json()
        result = calculate_bridge_capacity(
            data["bridge_type"],
            float(data["span_length"]),
            data["material"],
            data["beam_section"],
            data["applied_loads"],
            data["safety_factors"]
        )
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 400

if __name__ == '__main__':
    app.run(debug=True)
