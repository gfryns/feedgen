import json
import os

STATE_FILE = "state.json"

class WizardStateManager:
    def __init__(self, filename=STATE_FILE):
        self.filename = filename
        self.data = self._load_state()
        self.insecure = False # In-memory flag
        
        # Master dependency graph
        self.dependencies = {
            'infra': ['config'],
            'dataset': ['infra'],
            'procedures': ['dataset'],
            'source': ['infra'],
            'filter': ['dataset', 'source'],
            'web': ['dataset', 'filter'],
            'images': ['dataset', 'filter'],
            'examples': ['dataset', 'filter'],
            'prepare': ['dataset', 'filter'],
            'gen': ['filter', 'procedures']
        }
        
        # Build reverse graph (who depends on whom) once at startup
        self.dependents = {}
        for child, parents in self.dependencies.items():
            for parent in parents:
                if parent not in self.dependents:
                    self.dependents[parent] = []
                self.dependents[parent].append(child)
        
    def _load_state(self):
        if os.path.exists(self.filename):
            with open(self.filename, 'r') as f:
                try:
                    return json.load(f)
                except json.JSONDecodeError:
                    return {}
        return {}
        
    def save(self):
        with open(self.filename, 'w') as f:
            json.dump(self.data, f, indent=4)
            
    def get(self, key, default=None):
        return self.data.get(key, default)
        
    def set(self, key, value, save=True):
        self.data[key] = value
        if save:
            self.save()

    def update_data(self, updates: dict):
        """Update multiple state values and save once."""
        self.data.update(updates)
        self.save()
        
    def get_step_status(self, step_name):
        return self.data.get('steps', {}).get(step_name, 'Pending')
        
    def set_step_status(self, step_name, status, save=True):
        if 'steps' not in self.data:
            self.data['steps'] = {}
        self.data['steps'][step_name] = status
        if save:
            self.save()
        
    def check_dependency(self, step_name):
        deps = self.dependencies.get(step_name, [])
        for dep in deps:
            if self.get_step_status(dep) != 'Completed':
                return False, f"Step '{dep}' must be completed before running '{step_name}'."
        return True, ""
        
    def invalidate_steps(self, steps_list):
        for dep in steps_list:
            if self.get_step_status(dep) == 'Completed':
                self.set_step_status(dep, 'Pending', save=False)
        self.save()
                
    def invalidate_descendants(self, step_name):
        """Find and reset all descendants of a step to 'Pending'."""
        to_invalidate = set()
        queue = [step_name]
        
        while queue:
            current = queue.pop(0)
            if current in self.dependents:
                for dep in self.dependents[current]:
                    if dep not in to_invalidate:
                        to_invalidate.add(dep)
                        queue.append(dep)
                        
        if to_invalidate:
            for dep in to_invalidate:
                if self.get_step_status(dep) == 'Completed':
                    self.set_step_status(dep, 'Pending', save=False)
            self.save()
