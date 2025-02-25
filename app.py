from flask import Flask, render_template, request
import math
import logging

app = Flask(__name__)
logging.basicConfig(level=logging.DEBUG)

# Make Python's built-in zip available to Jinja2 templates
app.jinja_env.globals.update(zip=zip)

def get_float(value, default=0.0):
    """Safely convert a value to float."""
    try:
        return float(value.strip()) if value and isinstance(value, str) else default
    except Exception:
        return default

def get_additional_load_sf(load_material):
    """Return the safety factor for an additional load based on its material."""
    if not load_material:
        return 1.0
    material = load_material.strip().lower()
    if material == "steel":
        return 1.05
    elif material in ["concrete", "timber"]:
        return 1.15
    else:
        return 1.0

def calculate_steel_capacity(steel_grade, flange_width, flange_thickness, web_thickness, web_depth, condition_factor):
    """
    Calculates the plastic moment capacity (Mpe) and shear capacity for a steel beam.
    Overall beam depth = web_depth + 2 * flange_thickness.
    Z_plastic = [flange_width * flange_thickness * (overall_depth - flange_thickness) +
                 (web_thickness * (overall_depth - 2*flange_thickness)**2)/4] / 1e6 (in m³)
    Mpe = (fy * Z_plastic * condition_factor) / (1.05 * 1.1)
    Shear capacity = (fy * web_thickness * overall_depth * condition_factor) / (1.73 * 1.05 * 1.1 * 1000)
    """
    steel_grade = steel_grade.strip()
    fy = 230.0 if steel_grade == "S230" else (275.0 if steel_grade == "S275" else 355.0)
    overall_depth = web_depth + 2 * flange_thickness
    Z_plastic = (flange_width * flange_thickness * (overall_depth - flange_thickness) +
                 (web_thickness * (overall_depth - 2 * flange_thickness)**2) / 4) / 1e6
    Mpe = (fy * Z_plastic * condition_factor) / (1.05 * 1.1)
    shear_capacity = (fy * web_thickness * overall_depth * condition_factor) / (1.73 * 1.05 * 1.1 * 1000)
    logging.debug(f"Steel: overall_depth={overall_depth} mm, Z_plastic={Z_plastic} m³, Mpe={Mpe} kNm, shear={shear_capacity} kN")
    return Mpe, shear_capacity

def calculate_concrete_capacity(concrete_grade, beam_width, total_depth, reinforcement_layers,
                                reinforcement_strength,
                                partial_factor_concrete=1.5, partial_factor_reinf=1.15,
                                partial_factor_shear=1.25):
    """
    Calculates design moment and ultimate shear capacities for a reinforced concrete beam.
    
    The user enters the beam’s total depth.
    reinforcement_layers is a list of dictionaries, each with:
       - num_bars: number of bars in that layer,
       - bar_diameter: in mm,
       - layer_cover: distance from the bottom of the beam to the centroid of the reinforcement.
    
    For "C32/40": f_ck = 30 MPa, fcu = 40 MPa; otherwise f_ck = 40 MPa, fcu = 50 MPa.
    f_cd = f_ck / partial_factor_concrete.
    f_y_design = reinforcement_strength / partial_factor_reinf.
    
    Total reinforcement area, As = sum(num_bars * (π/4 * (bar_diameter)^2)).
    Effective depth, d_eff = (sum(Ai * (total_depth - layer_cover)))/sum(Ai).
    
    Then:
      Mus = (f_y_design * As * (d_eff - a/2)) / 1e6, where a = (As * f_y_design) / (0.85*(fcu/partial_factor_concrete)*beam_width).
      Muc = [0.225*(fcu)/partial_factor_concrete] * beam_width * (d_eff)^2 / 1e6.
    Design moment capacity is min(Mus, Muc).
    
    Ultimate shear capacity, Vu:
      Ss = min((550/d_eff)**0.25, 1.0)
      vc = (0.24/partial_factor_shear) * (((100*As)/(beam_width*d_eff))**0.333 * (fcu**0.333))
      Vu = Ss * vc * beam_width * d_eff (converted to kN)
    """
    if concrete_grade == "C32/40":
        f_ck = 30
        fcu = 40
    else:
        f_ck = 40
        fcu = 50
    f_cd = f_ck / partial_factor_concrete
    f_y_design = reinforcement_strength / partial_factor_reinf

    total_As = 0.0
    weighted_depth = 0.0
    for num, dia, cover in zip(
        request.form.getlist("reinforcement_num[]"),
        request.form.getlist("reinforcement_diameter[]"),
        request.form.getlist("reinforcement_cover[]")
    ):
        if num != "" and dia != "" and cover != "":
            cover_val = get_float(cover)
            if cover_val >= total_depth:
                raise ValueError("Invalid reinforcement cover: cover must be less than total depth.")
            A_layer = int(num) * (math.pi / 4) * (get_float(dia) ** 2)
            total_As += A_layer
            d_layer = total_depth - cover_val
            weighted_depth += A_layer * d_layer
    if total_As == 0:
        raise ValueError("No reinforcement provided. Please enter valid reinforcement details.")
    d_eff = weighted_depth / total_As

    a_val = (total_As * f_y_design) / (0.85 * (fcu / partial_factor_concrete) * beam_width)
    Mus = (f_y_design * total_As * (d_eff - a_val/2)) / 1e6
    Muc = (0.225 * fcu / partial_factor_concrete) * beam_width * (d_eff ** 2) / 1e6
    moment_capacity = min(Mus, Muc)
    
    Ss = (550 / d_eff) ** 0.25
    if Ss > 1.0:
        Ss = 1.0
    vc = (0.24 / partial_factor_shear) * (((100 * total_As) / (beam_width * d_eff)) ** 0.333 * (fcu ** 0.333))
    Vu = Ss * vc * beam_width * d_eff
    Vu_kN = Vu / 1000.0

    logging.debug(f"Concrete: f_ck={f_ck}, fcu={fcu}, f_cd={f_cd}, f_y_design={f_y_design}")
    logging.debug(f"Reinf: total_As={total_As:.2f} mm², weighted_depth={weighted_depth:.2f} mm, d_eff={d_eff:.2f} mm, a={a_val:.2f} mm")
    logging.debug(f"Mus = {Mus:.6f} kNm, Muc = {Muc:.6f} kNm, chosen moment_capacity = {moment_capacity:.6f} kNm")
    logging.debug(f"Ultimate Shear: Ss = {Ss:.4f}, vc = {vc:.4f}, Vu = {Vu_kN:.6f} kN")
    
    return moment_capacity, Vu_kN, Mus, Muc, d_eff, total_As

def calculate_effective_length(L, k1=1.0, k2=1.0):
    return k1 * k2 * L

def calculate_radius_of_gyration_strong(B_f, t_f, t_w, web_depth):
    d = web_depth + 2 * t_f
    A = 2 * (B_f * t_f) + t_w * (d - 2 * t_f)
    I_x = (t_w ** 3 * (d - 2 * t_f)) / 12.0 + 2 * ((t_f * (B_f ** 3)) / 12.0)
    r_x = math.sqrt(I_x / A)
    logging.debug(f"Strong axis: A={A} mm², I_x={I_x} mm⁴, r_x={r_x} mm")
    return r_x / 1000.0

lookup_table = {
    0: 1.000000,
    40: 0.900000,
    50: 0.798750,
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
            logging.debug(f"X={X}, Lookup Factor={factor}")
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
        return 1.0
    if F >= 20:
        return table[20]
    lower = int(math.floor(F))
    upper = lower + 1
    fraction = F - lower
    v_val = table[lower] + fraction * (table[upper] - table[lower])
    logging.debug(f"F={F}, v={v_val}")
    return v_val

def calculate_slenderness(effective_length, web_depth, flange_thickness, B_f, t_w):
    r = calculate_radius_of_gyration_strong(B_f, flange_thickness, t_w, web_depth)
    d = web_depth + 2 * flange_thickness
    F_param = (effective_length * flange_thickness) / (r * d)
    v = calculate_v_from_F(F_param)
    slenderness = (effective_length / r) * v
    logging.debug(f"Effective Length={effective_length}, r={r}, F={F_param}, v={v}, slenderness={slenderness}")
    return slenderness, F_param, v, r

def calculate_bd37_moment_capacity(Mpe, effective_length, steel_grade, flange_width, flange_thickness, web_thickness, web_depth):
    fy = 230.0 if steel_grade.strip() == "S230" else (275.0 if steel_grade.strip() == "S275" else 355.0)
    slenderness, F_param, v_value, r = calculate_slenderness(effective_length, web_depth, flange_thickness, flange_width, web_thickness)
    X = slenderness * math.sqrt(fy / 355.0) if Mpe != 0 else 0.0
    lookup_factor = get_lookup_factor(X)
    MR = lookup_factor * Mpe
    logging.debug(f"Steel: fy={fy}, slenderness={slenderness}, X={X}, Lookup Factor={lookup_factor}, MR={MR}")
    return MR, slenderness, X

def calculate_vehicle_loads(span_length, vehicle_type, impact_factor=1.0, wheel_dispersion="none", axle_mode="per beam"):
    vt = vehicle_type.strip().lower()
    if vt == "3 tonne":
        spacing = 2.0
        P1 = 21.0
        P2 = 9.0
    elif vt == "7.5 tonne":
        spacing = 2.0
        P1 = 59.0
        P2 = 15.0
    elif vt == "18 tonne":
        spacing = 3.0
        P1 = 64.0
        P2 = 113.0
    else:
        return {"Vehicle Maximum Moment (kNm)": 0.0, "Vehicle Maximum Shear (kN)": 0.0}
    if axle_mode.strip().lower() == "per beam":
        P1 /= 2.0
        P2 /= 2.0
    P1 *= 1.3
    P2 *= 1.3
    reduction_factor = 1.0
    try:
        rd = float(wheel_dispersion)
        if rd == 25:
            reduction_factor = 0.75
        elif rd == 50:
            reduction_factor = 0.5
    except:
        reduction_factor = 1.0
    P1 *= reduction_factor
    P2 *= reduction_factor
    worst_M = 0.0
    worst_V = 0.0
    a_step = 0.01
    x_step = 0.01
    L = span_length
    for a in drange(0, L - spacing, a_step):
        b = a + spacing
        R_A = (P1 * (L - a) + P2 * (L - b)) / L
        M_max_for_a = 0.0
        V_max_for_a = 0.0
        x = 0.0
        while x <= L:
            if x <= a:
                M = R_A * x
            elif x <= b:
                M = R_A * x - P1 * (x - a)
            else:
                M = R_A * x - P1 * (x - a) - P2 * (x - b)
            if x < a:
                V = R_A
            elif x < b:
                V = R_A - P1
            else:
                V = R_A - P1 - P2
            M_max_for_a = max(M_max_for_a, abs(M))
            V_max_for_a = max(V_max_for_a, abs(V))
            x += x_step
        worst_M = max(worst_M, M_max_for_a)
        worst_V = max(worst_V, V_max_for_a)
    worst_M *= impact_factor
    worst_V *= impact_factor
    return {"Vehicle Maximum Moment (kNm)": worst_M, "Vehicle Maximum Shear (kN)": worst_V}

def calculate_applied_loads(span_length, loading_type, additional_loads, loaded_width=None, access_factor=None, lane_width=None):
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
        try:
            load_value = load.get("value", 0)
            distribution = load.get("load_distribution", "").lower()
            if not distribution:
                distribution = ""
            load_type_str = load.get("type", "").lower() or "live"
            load_material = load.get("load_material", "steel").lower()
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
                sf = get_additional_load_sf(load_material)
                additional_dead += add_moment * sf
            else:
                additional_live += add_moment
            additional_shear += add_shear
        except Exception as e:
            logging.error(f"Error processing additional load: {load} - {e}")
    total_applied_moment = base_moment + additional_dead + additional_live
    total_applied_shear = (default_loads.get("effective_udl", 0) * span_length) / 2 + (kel if loading_type=="HA" else 0) + additional_shear
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
        total_depth = get_float(form_data.get("concrete_beam_depth"), "")
        if total_depth == 0:
            total_depth = get_float(form_data.get("beam_depth"), "")
        reinforcement_nums = request.form.getlist("reinforcement_num[]")
        reinforcement_diameters = request.form.getlist("reinforcement_diameter[]")
        reinforcement_covers = request.form.getlist("reinforcement_cover[]")
        reinforcement_strength = get_float(form_data.get("reinforcement_strength"), 500.0)
        reinforcement_layers = []
        for num, dia, cover in zip(reinforcement_nums, reinforcement_diameters, reinforcement_covers):
            if num != "" and dia != "" and cover != "":
                reinforcement_layers.append({
                    "num_bars": int(num),
                    "bar_diameter": get_float(dia),
                    "layer_cover": get_float(cover)
                })
        if not reinforcement_layers:
            return {"error": "No reinforcement provided. Please enter valid reinforcement details."}
        try:
            moment_capacity_conc, shear_capacity, Mus, Muc, d_eff, total_As = calculate_concrete_capacity(
                concrete_grade, beam_width, total_depth, reinforcement_layers,
                reinforcement_strength=reinforcement_strength
            )
        except Exception as e:
            return {"error": str(e)}
        moment_capacity = moment_capacity_conc
        effective_depth = d_eff
    else:
        moment_capacity, shear_capacity = 0, 0

    reduction_factor = 1.0
    if effective_length < span_length:
        reduction_factor = effective_length / span_length
        moment_capacity *= reduction_factor

    applied_moment, applied_shear, default_loads, additional_dead, additional_live = calculate_applied_loads(span_length, loading_type, loads, loaded_width, access_factor)
    
    self_weight_moment = 0.0
    if material == "Steel":
        A_steel = 2 * (flange_width * flange_thickness) + web_thickness * web_depth
        self_weight = (A_steel / 1e6) * 7850 * 9.81 / 1000
        self_weight_moment = ((self_weight * span_length**2) / 8) * 1.05

    total_applied_moment = applied_moment + self_weight_moment
    utilisation_ratio = total_applied_moment / moment_capacity if moment_capacity > 0 else float('inf')
    pass_fail = "Pass" if moment_capacity >= total_applied_moment and shear_capacity >= applied_shear else "Fail"

    applied_live = applied_moment - additional_dead
    applied_dead = additional_dead + self_weight_moment

    result = {
        "Span Length (m)": round(span_length, 1),
        "Effective Member Length (m)": round(effective_length, 1),
        "k1": round(k1, 1),
        "k2": round(k2, 1),
        "Reduction Factor": round(reduction_factor, 1),
        "Moment Capacity (kNm)": round(moment_capacity, 1),
        "Shear Capacity (kN)": round(shear_capacity, 1),
        "Applied Moment (ULS) (kNm)": round(total_applied_moment, 1),
        "Applied Shear (ULS) (kN)": round(applied_shear, 1),
        "Applied Live Load Moment (kNm)": round(applied_live, 1),
        "Applied Dead Load Moment (kNm)": round(applied_dead, 1),
        "Self Weight Moment (kNm)": round(self_weight_moment, 1),
        "Utilisation Ratio": round(utilisation_ratio, 1) if utilisation_ratio != float('inf') else "N/A",
        "Pass/Fail": pass_fail,
        "Loading Type": loading_type,
        "Condition Factor": round(condition_factor, 1),
        "Loaded Carriageway Width (m)": round(loaded_width, 1),
        "Access Type": access_str
    }
    if material == "Steel":
        slenderness, F_param, v, r = calculate_slenderness(effective_length, web_depth, flange_thickness, flange_width, web_thickness)
        result["Slenderness (λ)"] = round(slenderness, 1)
        result["X Parameter"] = round(slenderness * math.sqrt((230 if steel_grade=="S230" else (275 if steel_grade=="S275" else 355)) / 355.0), 1)
    if material == "Concrete":
        result["Mus (kNm)"] = round(Mus, 1)
        result["Muc (kNm)"] = round(Muc, 1)
        result["Effective Depth (mm)"] = round(effective_depth, 1)
        result["Total Reinforcement Area (mm²)"] = round(total_As, 1)
    if loading_type in ["HA", "HB"]:
        result[f"{loading_type} UDL (kN/m)"] = round(default_loads.get("effective_udl", 0), 1)
    if loading_type == "HA":
        result["HA KEL (kN)"] = round(default_loads.get("kel", 0), 1)
    
    vehicle_type = form_data.get("vehicle_type", "").strip()
    vehicle_impact_factor = get_float(form_data.get("vehicle_impact_factor"), 1.0)
    wheel_dispersion = form_data.get("wheel_dispersion", "none").strip()
    axle_mode = form_data.get("axle_load_mode", "per beam").strip()
    if vehicle_type and vehicle_type.lower() != "none":
        vehicle_results = calculate_vehicle_loads(span_length, vehicle_type, vehicle_impact_factor, wheel_dispersion, axle_mode)
        vehicle_results = {k: round(v, 1) for k, v in vehicle_results.items()}
        result.update(vehicle_results)
    
    result["Additional Loads"] = loads
    logging.debug("Calculation result: %s", result)
    return result

def drange(start, stop, step):
    r = start
    while r <= stop:
        yield r
        r += step

@app.route("/")
def home():
    return render_template("index.html", form_data={}, reinforcement_nums=[], reinforcement_diameters=[], reinforcement_covers=[])

@app.route("/calculate", methods=["POST"])
def calculate():
    form_data = request.form.to_dict()
    additional_loads = []
    load_desc_list = request.form.getlist("load_desc[]")
    load_value_list = request.form.getlist("load_value[]")
    load_type_list = request.form.getlist("load_type[]")
    load_distribution_list = request.form.getlist("load_distribution[]")
    load_material_list = request.form.getlist("load_material[]")
    
    for desc, value, ltype, distr, mat in zip(load_desc_list, load_value_list, load_type_list, load_distribution_list, load_material_list):
        if value.strip():
            additional_loads.append({
                "description": desc,
                "value": get_float(value),
                "type": ltype.lower(),
                "load_distribution": distr.lower(),
                "load_material": mat.lower()
            })
    
    reinforcement_nums = request.form.getlist("reinforcement_num[]")
    reinforcement_diameters = request.form.getlist("reinforcement_diameter[]")
    reinforcement_covers = request.form.getlist("reinforcement_cover[]")
    
    form_data["load_desc[]"] = load_desc_list
    form_data["load_value[]"] = load_value_list
    form_data["load_type[]"] = load_type_list
    form_data["load_distribution[]"] = load_distribution_list
    form_data["load_material[]"] = load_material_list

    result = calculate_beam_capacity(form_data, additional_loads)
    result["Additional Loads"] = additional_loads
    return render_template("index.html", result=result, form_data=form_data,
                           reinforcement_nums=reinforcement_nums,
                           reinforcement_diameters=reinforcement_diameters,
                           reinforcement_covers=reinforcement_covers)

if __name__ == "__main__":
    app.run(debug=True)
