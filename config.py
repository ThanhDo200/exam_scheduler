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
FAIRNESS_WEIGHT = 2000.0               # Ưu tiên fairness (minimize max-min shifts)
DISTANCE_WEIGHT = 200.0                # Ưu tiên minimize khoảng cách
GENDER_WEIGHT = 100.0                  # Nữ trực ít hơn nam (weight cao)
AGE_WEIGHT = 300.0                     # Cán bộ cao tuổi trực ít hơn
REST_TIME_WEIGHT = -400.0             # Negative weight to maximize rest gap between assigned MS_CA slots
SAME_DAY_DIFF_FACILITY_WEIGHT = 600.0  # Penalize multiple shifts same day across different facilities


# Gender mapping
GENDER_MALE = 'Nam'
GENDER_FEMALE = 'Nữ'
