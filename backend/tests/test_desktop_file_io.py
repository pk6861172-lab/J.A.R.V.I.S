import os
import unittest
from backend.desktop_automation.utils import write_text_file, read_text_file

class DesktopFileIOTests(unittest.TestCase):
    def test_write_and_read_text_file(self):
        path = os.path.join(os.path.dirname(__file__), 'tmp_test_file.txt')
        try:
            ok = write_text_file(path, 'hello JARVIS')
            self.assertTrue(ok)
            content = read_text_file(path)
            self.assertEqual(content, 'hello JARVIS')
        finally:
            if os.path.exists(path):
                os.remove(path)

if __name__ == '__main__':
    unittest.main()
