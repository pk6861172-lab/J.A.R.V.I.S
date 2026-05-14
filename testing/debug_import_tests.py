import os, sys, importlib.util, traceback
proj_root = r"C:\Users\PRASHANT\OneDrive\Desktop\J.A.R.V.I.S"
start_dir = os.path.join(proj_root, 'backend')
print('Start dir:', start_dir)
for root, dirs, files in os.walk(start_dir):
    for f in files:
        if f.startswith('test_') and f.endswith('.py'):
            path = os.path.join(root, f)
            print('\nFound test file:', path)
            try:
                spec = importlib.util.spec_from_file_location(f[:-3], path)
                mod = importlib.util.module_from_spec(spec)
                sys.modules[spec.name] = mod
                spec.loader.exec_module(mod)
                print('Imported', spec.name)
                import unittest
                cases = [name for name,obj in vars(mod).items() if isinstance(obj, type) and issubclass(obj, unittest.TestCase)]
                print('TestCase classes found:', cases)
            except Exception as e:
                print('Import failed:', e)
                traceback.print_exc()
print('\nSys.path:')
print('\n'.join(sys.path))
