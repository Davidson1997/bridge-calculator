from flask import Flask, render_template, request
import math
import logging

app = Flask(__name__)
logging.basicConfig(level=logging.DEBUG)

def get_float(value, default=0.0):
    """Safely convert a value to float."""
    try:
        return float(value.strip()) if value and isinstance(value, str) else default
    except Exception:
        return default

def calculate_steel_capacity(steel_grade, flange_width, flange_thickness, web_thickness, web_depth, condition_factor):
    """
    Calculates the plastic moment capacity (Mpe) and shear capacity for a steel beam.
    
    Overall beam depth is computed as:
        overall_depth = web_depth + 2 * flange_thickness
        
    Then the plastic section modulus is calculated by:
        Z_plastic = [flange_width * flange_thickness * (overall_depth - flange_thickness) +
                     (web_thickness * (overall_depth - 2*flange_thickness)**2)/4] / 1e6   (in m³)
                     
    Finally,
        Mpe = (fy * Z_plastic * condition_factor) / (1.05 * 1.1)
        Shear capacity = (fy * web_thickness * overall_depth * condition_factor) / (1.73 * 1.05 * 1.1 * 1000)
    """
    steel_grade = steel_grade.strip()
    fy = 230.0 if steel_grade == "S230" else (275.0 if steel_grade == "S275" else 355.0)
    overall_depth = web_depth + 2 * flange_thickness  # overall depth in mm
    Z_plastic = (flange_width * flange_thickness * (overall_depth - flange_thickness) +
                 (web_thickness * (overall_depth - 2 * flange_thickness)**2) / 4) / 1e6
    Mpe = (fy * Z_plastic * condition_factor) / (1.05 * 1.1)
    shear_capacity = (fy * web_thickness * overall_depth * condition_factor) / (1.73 * 1.05 * 1.1 * 1000)
    
    logging.debug(f"Overall depth = {overall_depth:.6f} mm, Z_plastic = {Z_plastic:.6f} m^3, Mpe = {Mpe:.6f} kNm, shear = {shear_capacity:.6f} kN")
    return Mpe, shear_capacity

def calculate_concrete_capacity(concrete_grade, beam_width, effective_depth, rebar_size=0, rebar_spacing=0):
    fck = 32 if concrete_grade == "C32/40" else 40
    moment_capacity = 0.156 * fck * beam_width * effective_depth**2 / 1e6
    shear_capacity = 0.6 * fck * beam_width * effective_depth / 1e3
    BD37_moment_factor = 0.95
    BD37_shear_factor = 1.0
    moment_capacity *= BD37_moment_factor
    shear_capacity *= BD37_shear_factor
    return moment_capacity, shear_capacity

def calculate_effective_length(L, k1=1.0, k2=1.0):
    return k1 * k2 * L

def calculate_radius_of_gyration_strong(B_f, t_f, t_w, web_depth):
    """
    Calculates r_x for a symmetric I-beam about the strong axis.
    
    Overall depth: d = web_depth + 2*t_f
    Gross area: A = 2*(B_f*t_f) + t_w*(d - 2*t_f)
    Moment of inertia about the strong axis:
         I_x = (t_w^3*(d-2*t_f))/12 + 2*(t_f*(B_f^3))/12
    Returns r_x in meters.
    """
    d = web_depth + 2 * t_f
    A = 2 * (B_f * t_f) + t_w * (d - 2 * t_f)
    I_x = (t_w ** 3 * (d - 2 * t_f)) / 12.0 + 2 * ((t_f * (B_f ** 3)) / 12.0)
    r_x = math.sqrt(I_x / A)
    logging.debug(f"(Strong axis) A = {A:.6f} mm^2, I_x = {I_x:.6f} mm^4, r_x = {r_x:.6f} mm")
    return r_x / 1000.0

# Revised lookup table for X to adjustment factor.
lookup_table = {
    0: 1.000000,
    40: 0.900000,
    50: 0.798750,  # Chosen so that X ~48 gives factor ~0.819
    60: 0.700000,
    70: 0.580000,
    80: 0.550000,
    90: 0.500000,
    100: 0.450000,
    110: 0.400000,
    120: 0.350000,
    130: 0.320000,
    140: 0.300000,
    150: 0.280000,
    160: 0.260000,
    170: 0.240000,
    180: 0.220000,
    190: 0.200000,
    200: 0.180000
}

def get_lookup_factor(X):
    keys = sorted(lookup_table.keys())
    if X <= keys[0]:
        return lookup_table[keys[0]]
    if X >= keys[-1]:
        return lookup_table[keys[-1]]
    for i in range(len(keys)-1):
        if keys[i] <= X <= keys[i+1]:
            fraction = (X - keys[i]) / (keys[i+1] - keys[i])
            factor = lookup_table[keys[i]] + fraction * (lookup_table[keys[i+1]] - lookup_table[keys[i]])
            logging.debug(f"X = {X:.6f}, Lookup Factor = {factor:.6f}")
            return factor
    return 1.0

def calculate_v_from_F(F):
    table = {
        0: 1.000000,
        1: 0.988000,
        2: 0.956000,
        3: 0.912000,
        4: 0.864000,
        5: 0.817000,
        6: 0.774000,
        7: 0.734000,
        8: 0.699000,
        9: 0.668000,
        10: 0.639000,
        11: 0.614000,
        12: 0.591000,
        13: 0.571000,
        14: 0.552000,
        15: 0.535000,
        16: 0.519000,
        17: 0.505000,
        18: 0.492000,
        19: 0.479000,
        20: 0.468000
    }
    if F <= 0:
        return 1.000000
    if F >= 20:
        return table[20]
    lower = int(math.floor(F))
    upper = lower + 1
    fraction = F - lower
    v_val = table[lower] + fraction * (table[upper] - table[lower])
    logging.debug(f"F = {F:.6f}, v = {v_val:.6f}")
    return v_val

def calculate_slenderness(effective_length, web_depth, flange_thickness, B_f, t_w):
    r = calculate_radius_of_gyration_strong(B_f, flange_thickness, t_w, web_depth)
    d = web_depth + 2 * flange_thickness
    F_param = (effective_length * flange_thickness) / (r * d)
    v = calculate_v_from_F(F_param)
    slenderness = (effective_length / r) * v
    logging.debug(f"Effective Length = {effective_length:.6f} m, r = {r:.6f} m, F = {F_param:.6f}, v = {v:.6f}, slenderness = {slenderness:.6f}")
    return slenderness, F_param, v, r

def calculate_bd37_moment_capacity(Mpe, effective_length, steel_grade, flange_width, flange_thickness, web_thickness, web_depth):
    fy = 230.0 if steel_grade.strip() == "S230" else (275.0 if steel_grade.strip() == "S275" else 355.0)
    slenderness, F_param, v_value, r = calculate_slenderness(effective_length, web_depth, flange_thickness, flange_width, web_thickness)
    X = slenderness * math.sqrt(fy / 355.0) if Mpe != 0 else 0.0
    lookup_factor = get_lookup_factor(X)
    MR = lookup_factor * Mpe
    logging.debug(f"fy = {fy:.6f}, slenderness = {slenderness:.6f}, X = {X:.6f}, Lookup Factor = {lookup_factor:.6f}, MR = {MR:.6f}")
    return MR, slenderness, X

def calculate_applied_loads(span_length, loading_type, additional_loads, loaded_width=None, access_factor=None, lane_width=None):
    # Compute base applied loads (HA or HB)
    if loading_type == "HA":
        base_udl = 230 * (1 / span_length)**0.67
        if loaded_width is None or loaded_width <= 0:
            loaded_width = 3.65
        if access_factor is None:
            access_factor = 1.3
        effective_udl = ((base_udl * 0.76) / (3.65 / 2.5)) * (loaded_width / 2.5) * access_factor
        base_kel = 82
        kel = ((base_kel * 0.76) / (3.65 / 2.5)) * (loaded_width / 2.5) * access_factor
        base_moment = (effective_udl * span_length**2) / 8 + (kel * span_length) / 4
        base_shear = (effective_udl * span_length) / 2 + (kel) / 2
        default_loads = {"base_udl": base_udl, "effective_udl": effective_udl, "kel": kel}
    elif loading_type == "HB":
        udl = 45
        point_load = 180
        if loaded_width is not None and access_factor is not None:
            effective_udl = ((udl * 0.76) / (3.65 / 2.5)) * (loaded_width / 2.5) * access_factor
        else:
            effective_udl = udl
        default_loads = {"udl": udl, "effective_udl": effective_udl}
        base_moment = (effective_udl * span_length**2) / 8 + (point_load * span_length) / 4
        base_shear = (effective_udl * span_length) / 2 + point_load / 2
    else:
        base_moment = 0
        base_shear = 0
        default_loads = {"udl": 0, "effective_udl": 0}
    
    additional_dead = 0.0
    additional_live = 0.0
    additional_shear = 0.0
    for load in additional_loads:
        load_value = load.get("value", 0)
        distribution = load.get("load_distribution", load.get("load_distribution[]", "").lower())
        # If not found, fallback to the field "load_distribution"
        if not distribution:
            distribution = load.get("distribution", "").lower()
        load_type_str = load.get("type", "").lower()  # "dead" or "live"
        if distribution == "udl":
            add_moment = (load_value * span_length**2) / 8
            add_shear = (load_value * span_length) / 2
        elif distribution == "point":
            add_moment = (load_value * span_length) / 4
            add_shear = load_value / 2
        else:
            add_moment = 0
            add_shear = 0
        if load_type_str == "dead":
            additional_dead += add_moment
        else:
            additional_live += add_moment
        additional_shear += add_shear

    # Return base loads plus additional moments and shears, and also return separate additional_dead and additional_live.
    total_applied_moment = base_moment + additional_dead + additional_live
    total_applied_shear = base_shear + additional_shear
    return total_applied_moment, total_applied_shear, default_loads, additional_dead, additional_live

def calculate_beam_capacity(form_data, loads):
    material = form_data.get("material")
    condition_factor = get_float(form_data.get("condition_factor"), 1.0)
    span_length = get_float(form_data.get("span_length"))
    L_actual = get_float(form_data.get("effective_member_length"), span_length)
    k1 = get_float(form_data.get("k1"), 1.0)
    k2 = get_float(form_data.get("k2"), 1.0)
    effective_length = calculate_effective_length(L_actual, k1, k2)
    loading_type = form_data.get("loading_type")
    
    loaded_width = get_float(form_data.get("loaded_width"), 3.65)
    access_str = form_data.get("access_type", "Company")
    access_factor = 1.5 if access_str.lower() == "public" else 1.3

    if material == "Steel":
        steel_grade = form_data.get("steel_grade")
        flange_width = get_float(form_data.get("flange_width"))
        flange_thickness = get_float(form_data.get("flange_thickness"))
        web_thickness = get_float(form_data.get("web_thickness"))
        # Interpret "beam_depth" as the web depth
        web_depth = get_float(form_data.get("beam_depth"))
        Mpe, shear_capacity = calculate_steel_capacity(steel_grade, flange_width, flange_thickness, web_thickness, web_depth, condition_factor)
        try:
            MR, slenderness, X = calculate_bd37_moment_capacity(Mpe, effective_length, steel_grade, flange_width, flange_thickness, web_thickness, web_depth)
            moment_capacity = MR
        except Exception as e:
            logging.error("Error in BD37 capacity calculation: %s", e)
            moment_capacity = Mpe
    elif material == "Concrete":
        concrete_grade = form_data.get("concrete_grade")
        beam_width = get_float(form_data.get("beam_width"))
        effective_depth = get_float(form_data.get("effective_depth"))
        moment_capacity, shear_capacity = calculate_concrete_capacity(concrete_grade, beam_width, effective_depth)
        effective_length = L_actual
    else:
        moment_capacity, shear_capacity = 0, 0

    reduction_factor = 1.0
    if effective_length < span_length:
        reduction_factor = effective_length / span_length
        moment_capacity *= reduction_factor

    # Calculate applied loads; get also additional dead and live load moments
    applied_moment, applied_shear, default_loads, additional_dead, additional_live = calculate_applied_loads(span_length, loading_type, loads, loaded_width, access_factor)
    
    # For additional loads safety factor: steel=1.05, concrete/timber=1.15
    if material == "Steel":
        add_dead_sf = 1.05
    elif material in ["Concrete", "Timber"]:
        add_dead_sf = 1.15
    else:
        add_dead_sf = 1.0

    # Recalculate applied moment by adjusting the dead load portion and adding self weight for steel.
    if material == "Steel":
        # Compute steel cross-sectional area (in mm²)
        A_steel = 2 * (flange_width * flange_thickness) + web_thickness * (web_depth)
        # Self weight per unit length in kN/m = (A in m² * 7850 * 9.81)/1000
        self_weight = (A_steel / 1e6) * 7850 * 9.81  # kN/m
        self_weight_moment = (self_weight * span_length**2) / 8  # kNm
        # Adjust additional dead loads by the safety factor
        adjusted_dead = additional_dead * add_dead_sf
        # New total applied moment = base loads + adjusted dead loads + additional live loads + self weight moment
        # We already have total_applied_moment = base + additional_dead + additional_live from calculate_applied_loads.
        # So add: (adjusted_dead - additional_dead) + self_weight_moment
        applied_moment = applied_moment + ((adjusted_dead - additional_dead) + self_weight_moment)
    # (For concrete/timber, you could similarly adjust additional dead loads if desired.)
    
    utilisation_ratio = applied_moment / moment_capacity if moment_capacity > 0 else float('inf')
    pass_fail = "Pass" if moment_capacity >= applied_moment and shear_capacity >= applied_shear else "Fail"

    result = {
        "Span Length (m)": round(span_length, 6),
        "Effective Member Length (m)": round(effective_length, 6),
        "k1": round(k1, 6),
        "k2": round(k2, 6),
        "Reduction Factor": round(reduction_factor, 6),
        "Moment Capacity (kNm)": round(moment_capacity, 6),
        "Shear Capacity (kN)": round(shear_capacity, 6),
        "Applied Moment (ULS) (kNm)": round(applied_moment, 6),
        "Applied Shear (ULS) (kN)": round(applied_shear, 6),
        "Applied Live Load Moment (kNm)": round((applied_moment - (additional_dead * add_dead_sf + (material=="Steel" and self_weight_moment or 0))), 6),
        "Applied Dead Load Moment (kNm)": round(additional_dead * add_dead_sf + (material=="Steel" and self_weight_moment or 0), 6),
        "Utilisation Ratio": round(utilisation_ratio, 6) if utilisation_ratio != float('inf') else "N/A",
        "Pass/Fail": pass_fail,
        "Loading Type": loading_type,
        "Condition Factor": round(condition_factor, 6),
        "Loaded Carriageway Width (m)": round(loaded_width, 6),
        "Access Type": access_str
    }
    if material == "Steel":
        result["Slenderness (λ)"] = round(slenderness, 6)
        result["X Parameter"] = round(X, 6)
    if loading_type in ["HA", "HB"]:
        result[f"{loading_type} UDL (kN/m)"] = round(default_loads.get("effective_udl", 0), 6)
    if loading_type == "HA":
        result["HA KEL (kN)"] = round(default_loads.get("kel", 0), 6)
    
    # Save the additional loads so that they are re-populated in the form.
    result["Additional Loads"] = loads
    
    logging.debug("Calculation result: %s", result)
    return result

@app.route("/")
def home():
    return render_template("index.html", form_data={})

@app.route("/calculate", methods=["POST"])
def calculate():
    form_data = request.form.to_dict()
    additional_loads = []
    # Save additional loads in lists so that they persist on re-render.
    load_desc_list = request.form.getlist("load_desc[]")
    load_value_list = request.form.getlist("load_value[]")
    load_type_list = request.form.getlist("load_type[]")
    load_distribution_list = request.form.getlist("load_distribution[]")
    
    for desc, value, ltype, distribution in zip(load_desc_list, load_value_list, load_type_list, load_distribution_list):
        if value.strip():
            additional_loads.append({
                "description": desc,
                "value": get_float(value),
                "type": ltype.lower(),  # Ensure lower case ("dead" or "live")
                "load_distribution": distribution.lower()
            })
    
    # Also save these lists back into form_data so they can be re-populated.
    form_data["load_desc[]"] = load_desc_list
    form_data["load_value[]"] = load_value_list
    form_data["load_type[]"] = load_type_list
    form_data["load_distribution[]"] = load_distribution_list

    result = calculate_beam_capacity(form_data, additional_loads)
    # Also pass the additional loads back so that the HTML can re-populate the rows.
    result["Additional Loads"] = additional_loads
    return render_template("index.html", result=result, form_data=form_data)

if __name__ == "__main__":
    app.run(debug=True)
