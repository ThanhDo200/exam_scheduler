"""
constraints.py - Define hard and soft constraints for the scheduling model
"""
import config
import pandas as pd
from pulp import LpVariable

FACILITY_DISTANCE_MAP = {
    'Cơ sở 1': 'KC CS1 (km)',
    'Cơ sở 2': 'KC CS2 (km)',
}


def add_hard_constraints(prob, assignment_vars, staff_data, shift_data):
    for ca in shift_data['UNIQUE_KEY']:
        shift_row = shift_data.loc[shift_data['UNIQUE_KEY'] == ca]
        if shift_row.empty:
            continue

        num_staff = 1
        if 'Số cán bộ cần thiết' in shift_row.columns:
            num_staff = int(shift_row['Số cán bộ cần thiết'].squeeze())

        staff_in_shift = [assignment_vars[cb][ca]
                          for cb in staff_data['MS_CB']
                          if ca in assignment_vars[cb]]
        if staff_in_shift:
            prob += sum(staff_in_shift) == num_staff, f"exact_people_shift_{ca}"

    if 'MS_CA' in shift_data.columns:
        ms_ca_groups = shift_data.groupby('MS_CA')['UNIQUE_KEY'].apply(list).to_dict()
        for cb in staff_data['MS_CB']:
            if cb not in assignment_vars:
                continue
            for ms_ca, unique_keys in ms_ca_groups.items():
                assigned_same_time = [assignment_vars[cb][ca]
                                      for ca in unique_keys
                                      if ca in assignment_vars[cb]]
                if assigned_same_time:
                    prob += sum(assigned_same_time) <= 1, f"no_duplicate_ms_ca_{cb}_{ms_ca}"

    print("OK Hard constraints added: exact people per shift and no duplicate MS_CA per staff")
    return prob


def add_objective(prob, assignment_vars, staff_data, shift_data):
    objective = 0

    objective += get_distance_penalty(assignment_vars, staff_data, shift_data)
    objective += get_gender_penalty(assignment_vars, staff_data, shift_data)
    objective += get_age_penalty(assignment_vars, staff_data, shift_data)

    objective += get_fairness_penalty(prob, assignment_vars, staff_data, shift_data)
    objective += get_same_day_diff_facility_penalty(prob, assignment_vars, staff_data, shift_data)
    objective += get_rest_gap_penalty(prob, assignment_vars, staff_data, shift_data)

    prob += objective, "Total_Cost"
    return prob


def get_fairness_penalty(prob, assignment_vars, staff_data, shift_data):
    # Penalize deviation from the average shift load per staff.
    total_required = 0
    if 'Số cán bộ cần thiết' in shift_data.columns:
        total_required = int(shift_data['Số cán bộ cần thiết'].fillna(1).sum())
    else:
        total_required = len(shift_data)

    avg_shifts = total_required / len(staff_data)
    fairness_cost = 0

    for cb in staff_data['MS_CB']:
        staff_shifts = [assignment_vars[cb][ca]
                        for ca in shift_data['UNIQUE_KEY']
                        if ca in assignment_vars[cb]]
        if not staff_shifts:
            continue

        shift_sum = sum(staff_shifts)
        over = LpVariable(f"over_{cb}", lowBound=0, cat='Continuous')
        under = LpVariable(f"under_{cb}", lowBound=0, cat='Continuous')

        prob += shift_sum - avg_shifts <= over, f"fairness_over_{cb}"
        prob += avg_shifts - shift_sum <= under, f"fairness_under_{cb}"
        prob += shift_sum >= 1, f"min_shift_count_{cb}"

        fairness_cost += config.FAIRNESS_WEIGHT * (over + under)

    return fairness_cost


def get_same_day_diff_facility_penalty(prob, assignment_vars, staff_data, shift_data):
    
    if 'MS_CA' not in shift_data.columns or 'Cơ sở' not in shift_data.columns:
        return 0

    shift_lookup = shift_data.set_index('UNIQUE_KEY')
    diff_fac_cost = 0

    for cb in staff_data['MS_CB']:
        if cb not in assignment_vars:
            continue

        facility_date_groups = {}
        for ca in shift_data['UNIQUE_KEY']:
            if ca not in assignment_vars[cb]:
                continue
            shift_row = shift_lookup.loc[ca]
            ms_ca = str(shift_row.get('MS_CA', ''))
            date_str = ms_ca.split('_')[0] if '_' in ms_ca else ms_ca
            facility = shift_row.get('Cơ sở', '')
            facility_date_groups.setdefault((cb, date_str, facility), []).append(ca)

        used_fac_vars = {}
        for (cb_key, date_str, facility), cas in facility_date_groups.items():
            used_fac = LpVariable(f"used_fac_{cb_key}_{date_str}_{facility}", cat='Binary')
            used_fac_vars[(cb_key, date_str, facility)] = used_fac
            for ca in cas:
                prob += used_fac >= assignment_vars[cb][ca], f"used_fac_lower_{cb_key}_{date_str}_{facility}_{ca}"
            prob += used_fac <= sum(assignment_vars[cb][ca] for ca in cas), f"used_fac_upper_{cb_key}_{date_str}_{facility}"

        date_facility_counts = {}
        for (cb_key, date_str, facility), cas in facility_date_groups.items():
            date_facility_counts.setdefault((cb_key, date_str), []).append(facility)

        for (cb_key, date_str), facilities in date_facility_counts.items():
            used_vars = [used_fac_vars[(cb_key, date_str, facility)] for facility in facilities]
            # If there are only two facilities on that date, create a single binary
            # that indicates both facilities are used (and penalize it). This avoids
            # introducing a continuous 'over' variable and reduces model size.
            if len(used_vars) == 2:
                a, b = used_vars
                both_used = LpVariable(f"same_day_diff_fac_both_{cb_key}_{date_str}", cat='Binary')
                prob += both_used <= a, f"same_day_diff_fac_both_le_{cb_key}_{date_str}_a"
                prob += both_used <= b, f"same_day_diff_fac_both_le_{cb_key}_{date_str}_b"
                prob += both_used >= a + b - 1, f"same_day_diff_fac_both_ge_{cb_key}_{date_str}"
                diff_fac_cost += config.SAME_DAY_DIFF_FACILITY_WEIGHT * both_used
            else:
                # Fallback for >2 facilities: keep simple continuous over variable
                facility_count = sum(used_vars)
                over_fac = LpVariable(f"same_day_diff_fac_over_{cb_key}_{date_str}", lowBound=0, cat='Continuous')
                prob += facility_count - 1 <= over_fac, f"same_day_diff_fac_over_constr_{cb_key}_{date_str}"
                diff_fac_cost += config.SAME_DAY_DIFF_FACILITY_WEIGHT * over_fac

    return diff_fac_cost


def get_rest_gap_penalty(prob, assignment_vars, staff_data, shift_data):

    if 'MS_CA' not in shift_data.columns:
        return 0

    time_map = {}
    for _, row in shift_data[['UNIQUE_KEY', 'MS_CA']].iterrows():
        ms_ca = str(row['MS_CA']).strip()
        normalized = ms_ca.replace('_', '')
        try:
            time_map[row['UNIQUE_KEY']] = int(normalized)
        except ValueError:
            continue

    if not time_map:
        return 0

    unique_times = sorted(set(time_map.values()))
    if len(unique_times) < 2:
        return 0

    rest_cost = 0
    time_vars = {}

    for cb in staff_data['MS_CB']:
        time_vars[cb] = {}
        for time_code in unique_times:
            time_vars[cb][time_code] = LpVariable(f"time_assign_{cb}_{time_code}", cat='Binary')

    # Link time assignment vars to shift assignments
    for cb in staff_data['MS_CB']:
        if cb not in assignment_vars:
            continue

        for ca, time_code in time_map.items():
            if ca not in assignment_vars[cb]:
                continue
            prob += time_vars[cb][time_code] >= assignment_vars[cb][ca], f"time_assign_lower_{cb}_{ca}"

        for time_code in unique_times:
            related_shifts = [ca for ca, tcode in time_map.items() if tcode == time_code and ca in assignment_vars[cb]]
            if not related_shifts:
                prob += time_vars[cb][time_code] == 0, f"time_assign_no_shifts_{cb}_{time_code}"
                continue
            prob += time_vars[cb][time_code] <= sum(assignment_vars[cb][ca] for ca in related_shifts), f"time_assign_upper_{cb}_{time_code}"

    # Only consider adjacent time codes to reduce variable/rule explosion
    for cb in staff_data['MS_CB']:
        if cb not in assignment_vars:
            continue

        for i in range(len(unique_times) - 1):
            first = unique_times[i]
            second = unique_times[i + 1]
            adj = LpVariable(f"rest_adj_{cb}_{first}_{second}", cat='Binary')
            prob += adj <= time_vars[cb][first], f"rest_adj_up1_{cb}_{first}_{second}"
            prob += adj <= time_vars[cb][second], f"rest_adj_up2_{cb}_{first}_{second}"
            prob += adj >= time_vars[cb][first] + time_vars[cb][second] - 1, f"rest_adj_low_{cb}_{first}_{second}"

            gap = second - first
            rest_cost += config.REST_TIME_WEIGHT * gap * adj

    return rest_cost


def get_distance_penalty(assignment_vars, staff_data, shift_data):
    if 'KC CS1 (km)' not in staff_data.columns and 'KC CS2 (km)' not in staff_data.columns:
        return 0

    facility_map = shift_data.set_index('UNIQUE_KEY')['Cơ sở'].to_dict()
    staff_lookup = staff_data.set_index('MS_CB')
    distance_cost = 0

    for cb in staff_data['MS_CB']:
        if cb not in staff_lookup.index:
            continue
        staff_row = staff_lookup.loc[cb]

        for ca in shift_data['UNIQUE_KEY']:
            if ca not in assignment_vars[cb]:
                continue

            facility = facility_map.get(ca)
            distance_col = FACILITY_DISTANCE_MAP.get(facility)
            if distance_col not in staff_row.index:
                continue

            distance = staff_row[distance_col]
            if pd.notna(distance):
                distance_cost += config.DISTANCE_WEIGHT * float(distance) * assignment_vars[cb].get(ca, 0)

    return distance_cost


def get_gender_penalty(assignment_vars, staff_data, shift_data):
    if 'Giới tính' not in staff_data.columns:
        return 0

    gender_map = staff_data.set_index('MS_CB')['Giới tính'].to_dict()
    gender_cost = 0

    for cb, gender in gender_map.items():
        if pd.isna(gender) or gender != config.GENDER_FEMALE:
            continue

        for ca in shift_data['UNIQUE_KEY']:
            if ca in assignment_vars[cb]:
                gender_cost += config.GENDER_WEIGHT * assignment_vars[cb].get(ca, 0)

    return gender_cost


def get_age_penalty(assignment_vars, staff_data, shift_data):
    if 'Tuổi' not in staff_data.columns:
        return 0

    ages = pd.to_numeric(staff_data.set_index('MS_CB')['Tuổi'], errors='coerce').to_dict()
    age_cost = 0

    for cb, age in ages.items():
        if pd.isna(age) or age < 55:
            continue

        age_penalty = config.AGE_WEIGHT * (age - 50) / 10
        for ca in shift_data['UNIQUE_KEY']:
            if ca in assignment_vars[cb]:
                age_cost += age_penalty * assignment_vars[cb].get(ca, 0)

    return age_cost

