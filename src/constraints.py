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

    print("OK Hard constraints added: exact people per shift")
    return prob


def add_objective(prob, assignment_vars, staff_data, shift_data):
    objective = 0

    objective += get_distance_penalty(assignment_vars, staff_data, shift_data)
    objective += get_gender_penalty(assignment_vars, staff_data, shift_data)
    objective += get_age_penalty(assignment_vars, staff_data, shift_data)

    fairness_cost = get_fairness_penalty(prob, assignment_vars, staff_data, shift_data)
    objective += fairness_cost
    
    overlap_cost = get_overlap_penalty(assignment_vars, staff_data, shift_data)
    objective += overlap_cost

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


def get_overlap_penalty(assignment_vars, staff_data, shift_data):
    # Penalize overlapping shifts on the same day at the same facility
    # Extract date from MS_ca (format: YYYYMMDD_X, take part before "_")
    
    if 'MS_ca' not in shift_data.columns or 'Cơ sở' not in shift_data.columns:
        return 0
    
    shift_lookup = shift_data.set_index('UNIQUE_KEY')
    overlap_cost = 0
    
    for cb in staff_data['MS_CB']:
        if cb not in assignment_vars:
            continue
        
        # Get all shifts assigned to this staff member
        assigned_shifts = [ca for ca in assignment_vars[cb] 
                          if assignment_vars[cb][ca].varValue == 1 
                          or (hasattr(assignment_vars[cb][ca], 'upBound') 
                              and assignment_vars[cb][ca].upBound == 1)]
        
        if len(assigned_shifts) <= 1:
            continue
        
        # Group shifts by date
        date_facility_count = {}
        for ca in assigned_shifts:
            if ca not in shift_lookup.index:
                continue
            
            shift_row = shift_lookup.loc[ca]
            # Extract date from MS_ca (part before "_")
            ms_ca = str(shift_row.get('MS_ca', ''))
            date_str = ms_ca.split('_')[0] if '_' in ms_ca else ms_ca
            facility = shift_row.get('Cơ sở', '')
            
            key = (date_str, facility)
            date_facility_count[key] = date_facility_count.get(key, 0) + 1
        
        # Calculate penalty: from 2nd occurrence onwards
        # 1st occurrence: 0 penalty
        # 2nd occurrence: +1 penalty
        # 3rd occurrence: +2 penalty, etc.
        for (date_str, facility), count in date_facility_count.items():
            if count >= 2:
                penalty = count - 1  # 2 shifts -> 1 penalty, 3 shifts -> 2 penalty
                overlap_cost += config.OVERLAP_WEIGHT * penalty if hasattr(config, 'OVERLAP_WEIGHT') else penalty
    
    return overlap_cost


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

