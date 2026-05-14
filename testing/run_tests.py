import os
import sys
import unittest
import importlib.util
import traceback

# Ensure project root on sys.path
proj_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if proj_root not in sys.path:
    sys.path.insert(0, proj_root)

print(f'Running backend tests with PYTHONPATH={proj_root}')
loader = unittest.TestLoader()
suite = unittest.TestSuite()

start_dir = os.path.join(proj_root, 'backend')
print('Scanning for test files under', start_dir)
count = 0
for root, dirs, files in os.walk(start_dir):
    for fname in files:
        if not (fname.startswith('test_') and fname.endswith('.py')):
            continue
        count += 1
        path = os.path.join(root, fname)
        rel = os.path.relpath(path, proj_root).replace(os.path.sep, '.')
        mod_name = rel[:-3]  # strip .py
        # Create a unique module name to avoid conflicts
        unique_mod_name = f'testfile_{count}_{mod_name.replace(".","_")}'
        print(f'Loading {path} as {unique_mod_name}')
        try:
            spec = importlib.util.spec_from_file_location(unique_mod_name, path)
            mod = importlib.util.module_from_spec(spec)
            sys.modules[unique_mod_name] = mod
            spec.loader.exec_module(mod)
            tests = loader.loadTestsFromModule(mod)
            if tests.countTestCases() > 0:
                suite.addTests(tests)
                print(f'  -> Loaded {tests.countTestCases()} tests')
            else:
                print('  -> No tests found in module')
        except Exception:
            print('  -> Import/run failed:')
            traceback.print_exc()

print(f'Found {count} test files, total collected tests: {suite.countTestCases()}')
runner = unittest.TextTestRunner(verbosity=2)
result = runner.run(suite)
sys.exit(0 if result.wasSuccessful() else 1)
