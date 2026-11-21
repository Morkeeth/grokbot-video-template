"""Built-in template looks registered in memory on the styles module.

Skip unless the Video Studio engine is present. No rendering.
"""
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, os.environ.get('TEST_MCP_DIR') or str(ROOT / 'MCP'))
sys.dont_write_bytecode = True
import studio_mcp as m  # noqa: E402

HAVE_STUDIO = bool(
    os.environ.get('STUDIO_PATH')
    or os.environ.get('HERMES_STUDIO_PATH')
    or (Path.home() / 'CODE/hermes-studio-connect').is_dir()
)


@unittest.skipUnless(HAVE_STUDIO, 'needs the Video Studio engine')
class TemplateLooks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.f, cls.s = m.studio()

    def test_three_names_accepted_and_listed(self):
        for name in ('quiet', 'oxblood', 'marker'):
            self.assertEqual(m.check_style(self.s, name), name)
        names = m.style_names(self.s)
        self.assertIn('quiet', names)
        self.assertIn('oxblood', names)
        self.assertIn('marker', names)

    def test_preset_box_none_and_exact_text_colour(self):
        cases = {
            'quiet': (255, 255, 255),
            'oxblood': (255, 190, 70),
            'marker': (255, 255, 255),
        }
        for name, text in cases.items():
            with self.subTest(name=name):
                st = m._preset(self.s, name)
                self.assertIsNone(st['box'])
                self.assertEqual(st['text'], text)

    def test_highlight_pinning(self):
        quiet = m._preset(self.s, 'quiet')
        oxblood = m._preset(self.s, 'oxblood')
        marker = m._preset(self.s, 'marker')
        self.assertIsNone(quiet['highlight'])
        self.assertIsNone(oxblood['highlight'])
        self.assertEqual(marker['highlight'], (0, 71, 255))

    def test_no_label_contains_hermes(self):
        for name in ('quiet', 'oxblood', 'marker'):
            with self.subTest(name=name):
                label = m.style_label(self.s, name)
                self.assertNotIn('hermes', label.lower())

    def test_engine_styles_file_unchanged(self):
        path = m.studio_path() / 'connectors' / 'styles.py'
        text = path.read_text()
        self.assertNotIn('oxblood', text)


if __name__ == '__main__':
    unittest.main()
