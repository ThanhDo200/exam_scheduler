import pandas as pd
import config


def load_staff_data(filepath=None):

    if filepath is None:
        filepath = config.INPUT_STAFF_FILE
    
    df = pd.read_excel(filepath)
    
    rename_map = {
        'MS của CÁN BỘ COI THI': 'MS_CB',
        'Tuổi': 'Tuổi',
        'Khoảng cách đến Cơ sở 1 (km)': 'KC CS1 (km)',
        'Khoảng cách đến Cơ sở 2 (km)': 'KC CS2 (km)'
    }
    df = df.rename(columns=rename_map, errors='ignore')
    
    if 'MS_CB' in df.columns:
        df['MS_CB'] = df['MS_CB'].astype(str).str.strip()
    if 'Giới tính' in df.columns:
        df['Giới tính'] = df['Giới tính'].astype(str).str.strip()
    
    if 'Tuổi' in df.columns and df['Tuổi'].notna().any():
        df['Tuổi'] = pd.to_numeric(df['Tuổi'], errors='coerce').fillna(df['Tuổi'].mean()).astype(int)

    if 'KC CS1 (km)' in df.columns:
        df['KC CS1 (km)'] = pd.to_numeric(df['KC CS1 (km)'], errors='coerce').fillna(df['KC CS1 (km)'].mean()).astype(float)
    
    if 'KC CS2 (km)' in df.columns:
        df['KC CS2 (km)'] = pd.to_numeric(df['KC CS2 (km)'], errors='coerce').fillna(df['KC CS2 (km)'].mean()).astype(float)

    return df

def load_shift_data(filepath=None):

    if filepath is None:
        filepath = config.INPUT_SHIFT_FILE
    
    df = pd.read_excel(filepath)
    
    rename_map = {
        'MS Ca thi': 'MS_CA',
        'GIỜ': 'Giờ',
        'Số lượng cán bộ cần thiết': 'Số cán bộ cần thiết'
    }
    df = df.rename(columns=rename_map)
    
    df['MS_CA'] = df['MS_CA'].astype(str).str.strip()
    df['Cơ sở'] = df['Cơ sở'].astype(str).str.strip()
    if 'Thứ' in df.columns:
        df['Thứ'] = df['Thứ'].astype(str).str.strip()
    
    if 'Số cán bộ cần thiết' in df.columns:
        df['Số cán bộ cần thiết'] = pd.to_numeric(df['Số cán bộ cần thiết'], errors='coerce').fillna(1).astype(int)
    
    df['UNIQUE_KEY'] = df['MS_CA'] + '_' + df['Cơ sở'].str.replace('Cơ sở ', 'CS')
    
    return df


def validate_data(staff_df, shift_df):

    staff_required = ['MS_CB', 'Giới tính', 'Tuổi', 'KC CS1 (km)', 'KC CS2 (km)']  # Adjust based on actual columns
    shift_required = ['UNIQUE_KEY'] 
    
    for col in staff_required:
        if col in staff_df.columns and staff_df[col].isnull().any():
            raise ValueError(f"Missing values in staff column: {col}")
    
    for col in shift_required:
        if col in shift_df.columns and shift_df[col].isnull().any():
            raise ValueError(f"Missing values in shift column: {col}")
    
    if 'MS_CB' in staff_df.columns and staff_df['MS_CB'].duplicated().any():
        raise ValueError("Duplicate staff IDs found after deduplication")
    
    if 'UNIQUE_KEY' in shift_df.columns and shift_df['UNIQUE_KEY'].duplicated().any():
        raise ValueError("Duplicate shift IDs found")
    
    print(f"OK Data validation passed: {len(staff_df)} staff, {len(shift_df)} shifts")
    return True


if __name__ == '__main__':
    staff_df = load_staff_data()
    shift_df = load_shift_data()
    print("Staff data shape:", staff_df.shape)
    print("Shift data shape:", shift_df.shape)
    print("\nStaff sample:")
    print(staff_df.head())
    print("\nShift sample:")
    print(shift_df.head())
