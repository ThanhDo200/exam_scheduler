from pulp import LpProblem, LpMinimize, LpStatus, LpVariable, PULP_CBC_CMD, value
import pandas as pd
from .constraints import add_hard_constraints, add_objective


class ExamSchedulerModel:

    def __init__(self, staff_data, shift_data):
        self.staff_data = staff_data
        self.shift_data = shift_data
        self.prob = None
        self.assignment_vars = {}
        self.solution = None

    def create_model(self):
        self.prob = LpProblem("Exam_Scheduler", LpMinimize)
        self._create_variables()
        self._add_hard_constraints()
        self._add_objective()
        print(f"OK Model created with {self.prob.numVariables()} variables")
        return self.prob

    def _create_variables(self):
        for cb in self.staff_data['MS_CB']:
            self.assignment_vars[cb] = {
                ca: LpVariable(f"assign_{cb}_{ca}", cat='Binary')
                for ca in self.shift_data['UNIQUE_KEY']
            }

    def _add_hard_constraints(self):
        add_hard_constraints(self.prob, self.assignment_vars, self.staff_data, self.shift_data)

    def _add_objective(self):
        add_objective(self.prob, self.assignment_vars, self.staff_data, self.shift_data)

    def solve(self, timeout=None):
        if self.prob is None:
            raise ValueError("Model not created yet. Call create_model() first.")

        print("\nSolving model ...")
        # Always create the CBC solver without a time limit so it can run to completion
        solver = PULP_CBC_CMD(msg=1)
        status = self.prob.solve(solver)

        print(f"OK Model solved with status: {LpStatus[status]}")
        try:
            obj_val = value(self.prob.objective)
            if obj_val is not None:
                print(f"  Objective value: {obj_val:.2f}")
            else:
                print("  Objective value: None")
        except Exception:
            print("  Objective value: unavailable")
        return status

    def extract_solution(self):
        if self.prob is None or value(self.prob.objective) is None:
            raise ValueError("Model not solved yet. Call solve() first.")

        assignments = [
            {'MS_CB': cb, 'UNIQUE_KEY': ca, 'Assigned': 1}
            for cb in self.staff_data['MS_CB']
            for ca in self.shift_data['UNIQUE_KEY']
            if value(self.assignment_vars[cb][ca]) == 1
        ]

        self.solution = pd.DataFrame(assignments, columns=['MS_CB', 'UNIQUE_KEY', 'Assigned'])
        print(f"OK Solution extracted: {len(self.solution)} assignments")
        return self.solution

    def get_summary_stats(self):
        if self.solution is None:
            return None

        assignments_per_staff = self.solution.groupby('MS_CB').size()
        return {
            'total_assignments': len(self.solution),
            'total_shifts': len(self.shift_data),
            'total_staff': len(self.staff_data),
            'average_staff_per_shift': len(self.solution) / len(self.shift_data),
            'max_shifts_per_staff': int(assignments_per_staff.max()),
            'min_shifts_per_staff': int(assignments_per_staff.min()),
            'avg_shifts_per_staff': float(assignments_per_staff.mean()),
        }


if __name__ == '__main__':
    from .loader import load_staff_data, load_shift_data
    
    staff = load_staff_data()
    shifts = load_shift_data()
    
    model = ExamSchedulerModel(staff, shifts)
    model.create_model()
    model.solve()
    model.extract_solution()
    
    print("\n📈 Solution Summary:")
    print(model.get_summary_stats())
