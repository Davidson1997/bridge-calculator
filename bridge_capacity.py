import math

def calculate_bridge_capacity(
    bridge_type: str,
    span_length: float,
    material: str,
    beam_section: str,
    applied_loads: dict,
    safety_factors: dict
):
    """
    Calculates the moment and shear capacities for a bridge based on input parameters.
    
    Parameters:
    - bridge_type (str): Type of bridge (Simply Supported, Cantilever, Continuous)
    - span_length (float): Length of the span in meters
    - material (str): Material type (Concrete, Steel, Composite)
    - beam_section (str): Beam section type (I-beam, Box Girder, etc.)
    - applied_loads (dict): Dictionary with load values (e.g., {"traffic": 50, "wind": 10})
    - safety_factors (dict): Dictionary with safety factors (e.g., {"steel": 1.05, "concrete": 1.3})
    
    Returns:
    - dict: Results containing moment, shear capacity, and pass/fail status
    """
    
    # Material properties (Example values - Should be refined based on Eurocode/BS)
    material_properties = {
        "Steel": {"fy": 355, "E": 210e3},  # Yield strength (MPa), Elastic modulus (MPa)
        "Concrete": {"fck": 30, "E": 30e3},
        "Composite": {"fck": 40, "fy": 275, "E": 180e3},
    }
    
    if material not in material_properties:
        raise ValueError("Material not recognized.")
    
    # Load factors
    load_factor = sum(applied_loads.values())
    
    # Basic Moment and Shear Capacity Calculations (Simplified)
    if bridge_type == "Simply Supported":
        moment_capacity = (load_factor * span_length ** 2) / 8
        shear_capacity = load_factor * span_length / 2
    elif bridge_type == "Cantilever":
        moment_capacity = (load_factor * span_length ** 2) / 2
        shear_capacity = load_factor * span_length
    else:
        raise ValueError("Unsupported bridge type.")
    
    # Apply material safety factor
    safety_factor = safety_factors.get(material.lower(), 1.0)
    moment_capacity /= safety_factor
    shear_capacity /= safety_factor
    
    # Check compliance (Placeholder logic for now)
    pass_fail = "Pass" if moment_capacity > shear_capacity else "Fail"
    
    return {
        "moment_capacity_kNm": round(moment_capacity, 2),
        "shear_capacity_kN": round(shear_capacity, 2),
        "pass_fail": pass_fail,
    }

# Example Usage
if __name__ == "__main__":
    test_bridge = {
        "bridge_type": "Simply Supported",
        "span_length": 20.0,
        "material": "Steel",
        "beam_section": "I-beam",
        "applied_loads": {"traffic": 50, "wind": 10},
        "safety_factors": {"steel": 1.05, "concrete": 1.3}
    }
    
    result = calculate_bridge_capacity(**test_bridge)
    print(result)
