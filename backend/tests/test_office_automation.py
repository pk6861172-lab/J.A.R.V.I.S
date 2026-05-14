import os
import unittest
from backend.connectors.office_advanced import create_excel_with_formulas, create_excel_and_open_in_excel

class OfficeAutomationTests(unittest.TestCase):
    def test_create_excel_with_formulas(self):
        path = os.path.join(os.path.dirname(__file__), 'tmp_formulas.xlsx')
        rows = [[1,2,'=A1+B1'], ['foo', 'bar', '=CONCAT(A2,B2)']]
        try:
            ok = create_excel_with_formulas(path, rows)
            self.assertTrue(ok)
            self.assertTrue(os.path.exists(path))
        finally:
            if os.path.exists(path):
                os.remove(path)

    def test_create_and_open_in_excel_skips_on_non_windows(self):
        path = os.path.join(os.path.dirname(__file__), 'tmp_formulas2.xlsx')
        rows = [[1,2,'=A1+B1']]
        try:
            ok = create_excel_and_open_in_excel(path, rows)
            self.assertTrue(ok)
            self.assertTrue(os.path.exists(path))
        finally:
            if os.path.exists(path):
                os.remove(path)

if __name__ == '__main__':
    unittest.main()
