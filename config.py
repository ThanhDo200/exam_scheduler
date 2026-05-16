import os

# Project paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')
OUTPUT_DIR = os.path.join(BASE_DIR, 'outputs')
SRC_DIR = os.path.join(BASE_DIR, 'src')

# Input data files
INPUT_STAFF_FILE = os.path.join(DATA_DIR, 'can_bo.xlsx')  # Danh sách cán bộ
INPUT_SHIFT_FILE = os.path.join(DATA_DIR, 'ca_thi.xlsx')  # Danh sách ca thi

# Output file
OUTPUT_SCHEDULE_FILE = os.path.join(OUTPUT_DIR, 'lich_truc_final.xlsx')

# Soft constraint weights (objective function)
FAIRNESS_WEIGHT = 2750.0               # Ưu tiên fairness (minimize max-min shifts)
DISTANCE_WEIGHT = 430.0                # Ưu tiên minimize khoảng cách
GENDER_WEIGHT = 500.0                  # Nữ trực ít hơn nam (weight cao)
AGE_WEIGHT = 1500.0                     # Cán bộ cao tuổi trực ít hơn           # Negative weight to maximize rest gap between assigned MS_CA slots
CLOSE_SHIFT_WEIGHT = 500.0             # Penalize two shifts that are too close together for the same staff
SAME_DAY_DIFF_FACILITY_WEIGHT = 1500.0  # Penalize multiple shifts same day across different facilities
MIN_SHIFT_WEIGHT = 900.0              # Penalize staff with zero assigned shifts
WEEKEND_WEIGHT = 700.0               # Penalize assignments on Saturday/Sunday
PARTNER_DIVERSITY_WEIGHT = 800.0       # Penalize repeated pairings of the same staff together

# Gender mapping
GENDER_MALE = 'Nam'
GENDER_FEMALE = 'Nữ'
