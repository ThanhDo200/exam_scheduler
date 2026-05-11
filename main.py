
import sys

from src.loader import load_staff_data, load_shift_data, validate_data
from src.model import ExamSchedulerModel
from src.exporter import export_to_excel
import config


def main():
    print("=" * 60)
    print("EXAM SCHEDULER - Toi uu lich truc coi thi")
    print("=" * 60)
    
    try:
        print("\nStep 1: Loading data...")
        staff_data = load_staff_data()
        shift_data = load_shift_data()
        print(f"  OK Loaded {len(staff_data)} staff and {len(shift_data)} shifts")
        
        print("\nStep 2: Validating data...")
        validate_data(staff_data, shift_data)
        
        print("\nStep 3: Creating optimization model...")
        model = ExamSchedulerModel(staff_data, shift_data)
        model.create_model()
        print(f"  OK Model has {model.prob.numConstraints()} constraints")
        
        print("\nStep 4: Solving model (this may take a moment)...")
        status = model.solve(timeout=300)
        
        if status != 1:  
            print(f"  ⚠ Warning: Model status is {status}. Solution may not be optimal.")
        
        print("\nStep 5: Extracting solution...")
        model.extract_solution()
        
        print("\nSolution Statistics:")
        stats = model.get_summary_stats()
        for key, value in stats.items():
            if isinstance(value, float):
                print(f"  • {key}: {value:.2f}")
            else:
                print(f"  • {key}: {value}")
        
        print("\nStep 7: Exporting results...")
        output_file = export_to_excel(model, staff_data, shift_data)
        
        print("\n" + "=" * 60)
        print("SUCCESS! Scheduling completed.")
        print(f"Output file: {output_file}")
        print("=" * 60)
        
        return 0
    
    except FileNotFoundError as e:
        print(f"\nERROR: Input file not found - {e}")
        print(f"   Check that these files exist:")
        print(f"   - {config.INPUT_STAFF_FILE}")
        print(f"   - {config.INPUT_SHIFT_FILE}")
        return 1
    
    except ValueError as e:
        print(f"\nERROR: {e}")
        return 1
    
    except Exception as e:
        print(f"\nERROR: Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    exit_code = main()
    sys.exit(exit_code)
