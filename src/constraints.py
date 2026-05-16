"""
constraints.py - Define hard and soft constraints for the scheduling model
"""
import config
import pandas as pd
from itertools import combinations
from pulp import LpVariable, lpSum

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

    if 'MS_CA' in shift_data.columns and 'Cơ sở' in shift_data.columns:
        shift_lookup = shift_data.set_index('UNIQUE_KEY')
        for cb in staff_data['MS_CB']:
            if cb not in assignment_vars:
                continue

            shifts_by_date = {}
            for ca in shift_data['UNIQUE_KEY']:
                if ca not in assignment_vars[cb]:
                    continue
                row = shift_lookup.loc[ca]
                ms_ca = str(row.get('MS_CA', ''))
                date_str = ms_ca.split('_')[0] if '_' in ms_ca else ms_ca
                facility = row.get('Cơ sở', '')
                time_code = 0
                try:
                    time_code = int(ms_ca.replace('_', ''))
                except ValueError:
                    pass
                shifts_by_date.setdefault(date_str, []).append((time_code, ca, facility))

            for date_str, entries in shifts_by_date.items():
                entries.sort(key=lambda x: x[0])
                for i in range(len(entries) - 1):
                    first_ca = entries[i][1]
                    first_fac = entries[i][2]
                    second_ca = entries[i + 1][1]
                    second_fac = entries[i + 1][2]
                    if first_fac and second_fac and first_fac != second_fac:
                        prob += assignment_vars[cb][first_ca] + assignment_vars[cb][second_ca] <= 1, \
                                 f"no_consecutive_diff_fac_{cb}_{date_str}_{first_ca}_{second_ca}"

    print("OK Hard constraints added: exact people per shift, no duplicate MS_CA per staff, and no consecutive different-facility shifts")
    return prob


def add_objective(prob, assignment_vars, staff_data, shift_data):
    objective = 0

    objective += get_distance_penalty(assignment_vars, staff_data, shift_data)
    objective += get_gender_penalty(assignment_vars, staff_data, shift_data)
    objective += get_age_penalty(assignment_vars, staff_data, shift_data)

    objective += get_fairness_penalty(prob, assignment_vars, staff_data, shift_data)
    objective += get_min_shift_penalty(prob, assignment_vars, staff_data, shift_data)
    objective += get_weekend_penalty(assignment_vars, staff_data, shift_data)
    # Partner diversity penalty: count total co-assigned shifts per staff-pair
    objective += get_partner_diversity_penalty(prob, assignment_vars, staff_data, shift_data)
    objective += get_same_day_diff_facility_penalty(prob, assignment_vars, staff_data, shift_data)
    objective += get_rest_gap_penalty(prob, assignment_vars, staff_data, shift_data)

    prob += objective, "Total_Cost"
    return prob


def get_fairness_penalty(prob, assignment_vars, staff_data, shift_data):

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

        fairness_cost += config.FAIRNESS_WEIGHT * (over + under)

    return fairness_cost


def get_min_shift_penalty(prob, assignment_vars, staff_data, shift_data):
    min_shift_cost = 0

    for cb in staff_data['MS_CB']:
        staff_shifts = [assignment_vars[cb][ca]
                        for ca in shift_data['UNIQUE_KEY']
                        if ca in assignment_vars[cb]]
        if not staff_shifts:
            continue

        shift_sum = sum(staff_shifts)
        min_shift_violation = LpVariable(f"min_shift_violation_{cb}", lowBound=0, cat='Continuous')
        prob += 1 - shift_sum <= min_shift_violation, f"min_shift_violation_def_{cb}"
        min_shift_cost += config.MIN_SHIFT_WEIGHT * min_shift_violation

    return min_shift_cost

def get_weekend_penalty(assignment_vars, staff_data, shift_data):

    if 'Thứ' not in shift_data.columns:
        return 0

    # Map UNIQUE_KEY -> day string
    day_map = shift_data.set_index('UNIQUE_KEY')['Thứ'].to_dict()
    weekend_keys = set()
    for uk, val in day_map.items():
        s = ' '.join(str(val).strip().lower().split())
        if not s:
            continue
        if s in ('Thứ 7', 'Chủ Nhật'):
            weekend_keys.add(uk)

    if not weekend_keys:
        return 0

    weekend_cost = 0
    for cb in staff_data['MS_CB']:
        if cb not in assignment_vars:
            continue
        for ca in weekend_keys:
            if ca in assignment_vars[cb]:
                weekend_cost += config.WEEKEND_WEIGHT * assignment_vars[cb].get(ca, 0)

    return weekend_cost


def get_partner_diversity_penalty(prob, assignment_vars, staff_data, shift_data):
    if len(staff_data) < 2 or 'UNIQUE_KEY' not in shift_data.columns:
        return 0

    partner_cost = 0
    staff_list = staff_data['MS_CB'].tolist()

    for cb1, cb2 in combinations(staff_list, 2):
        if cb1 not in assignment_vars or cb2 not in assignment_vars:
            continue

        common_vars = []
        for ca in shift_data['UNIQUE_KEY']:
            if ca in assignment_vars[cb1] and ca in assignment_vars[cb2]:
                common_var = LpVariable(f"pair_common_{cb1}_{cb2}_{ca}", cat='Binary')
                prob += common_var <= assignment_vars[cb1][ca], f"pair_common_le1_{cb1}_{cb2}_{ca}"
                prob += common_var <= assignment_vars[cb2][ca], f"pair_common_le2_{cb1}_{cb2}_{ca}"
                prob += common_var >= assignment_vars[cb1][ca] + assignment_vars[cb2][ca] - 1, f"pair_common_ge_{cb1}_{cb2}_{ca}"
                common_vars.append(common_var)

        if not common_vars:
            continue

        co_sum = lpSum(common_vars)
        pair_cost = LpVariable(f"pair_cost_{cb1}_{cb2}", lowBound=0, cat='Continuous')
        prob += pair_cost >= co_sum - 1, f"pair_cost_def_{cb1}_{cb2}"
        partner_cost += config.PARTNER_DIVERSITY_WEIGHT * pair_cost

    return partner_cost


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
            if len(used_vars) == 2:
                a, b = used_vars
                both_used = LpVariable(f"same_day_diff_fac_both_{cb_key}_{date_str}", cat='Binary')
                prob += both_used <= a, f"same_day_diff_fac_both_le_{cb_key}_{date_str}_a"
                prob += both_used <= b, f"same_day_diff_fac_both_le_{cb_key}_{date_str}_b"
                prob += both_used >= a + b - 1, f"same_day_diff_fac_both_ge_{cb_key}_{date_str}"
                diff_fac_cost += config.SAME_DAY_DIFF_FACILITY_WEIGHT * both_used
            else:
                facility_count = sum(used_vars)
                over_fac = LpVariable(f"same_day_diff_fac_over_{cb_key}_{date_str}", lowBound=0, cat='Continuous')
                prob += facility_count - 1 <= over_fac, f"same_day_diff_fac_over_constr_{cb_key}_{date_str}"
                diff_fac_cost += config.SAME_DAY_DIFF_FACILITY_WEIGHT * over_fac

    return diff_fac_cost


def get_rest_gap_penalty(prob, assignment_vars, staff_data, shift_data):

    if 'MS_CA' not in shift_data.columns:
        return 0

    date_time_map = {}
    for uk, ms_ca in shift_data.set_index('UNIQUE_KEY')['MS_CA'].dropna().items():
        ms_ca = str(ms_ca).strip()
        if '_' not in ms_ca:
            continue
        date_str, time_code_str = ms_ca.split('_', 1)
        try:
            date_time_map[uk] = (date_str, int(time_code_str))
        except ValueError:
            continue

    if not date_time_map:
        return 0

    rest_cost = 0
    for cb in staff_data['MS_CB']:
        if cb not in assignment_vars:
            continue

        shifts_by_date = {}
        for uk, (date_str, time_code) in date_time_map.items():
            if uk in assignment_vars[cb]:
                shifts_by_date.setdefault(date_str, []).append((time_code, uk))

        for date_str, entries in shifts_by_date.items():
            entries.sort()
            for i, (first_time, first_uk) in enumerate(entries):
                for second_time, second_uk in entries[i + 1:]:
                    gap = second_time - first_time
                    if gap > 2:
                        break
                    close_var = LpVariable(
                        f"rest_close_{cb}_{date_str}_{first_time}_{second_time}_{first_uk}_{second_uk}",
                        cat='Binary'
                    )
                    prob += close_var <= assignment_vars[cb][first_uk], f"rest_close_le1_{cb}_{date_str}_{first_time}_{second_time}_{first_uk}_{second_uk}"
                    prob += close_var <= assignment_vars[cb][second_uk], f"rest_close_le2_{cb}_{date_str}_{first_time}_{second_time}_{first_uk}_{second_uk}"
                    prob += close_var >= assignment_vars[cb][first_uk] + assignment_vars[cb][second_uk] - 1, f"rest_close_ge_{cb}_{date_str}_{first_time}_{second_time}_{first_uk}_{second_uk}"
                    rest_cost += config.CLOSE_SHIFT_WEIGHT * close_var

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
        if pd.isna(age) or age < 45:
            continue

        age_penalty = config.AGE_WEIGHT * (age - 50) / 10
        for ca in shift_data['UNIQUE_KEY']:
            if ca in assignment_vars[cb]:
                age_cost += age_penalty * assignment_vars[cb].get(ca, 0)

    return age_cost

