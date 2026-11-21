"""Built-in template looks registered in memory on the styles module.

Skip unless the Video Studio engine is present. No rendering.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

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


def tiny_clip(path):
    subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-y', '-f', 'lavfi', '-i', 'color=blue:s=108x192:d=0.5',
                    '-f', 'lavfi', '-i', 'sine=f=440:d=0.5', '-t', '0.5', '-c:v', 'libx264', '-pix_fmt', 'yuv420p',
                    '-c:a', 'aac', str(path)], check=True)
    return path


@unittest.skipUnless(HAVE_STUDIO, 'needs the Video Studio engine')
class CaptionsFromKeepsTheMark(unittest.TestCase):
    """Borrowing captions must bring the word highlight of that look, or drop the old one."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix='gbt-looks-'))
        self.env = mock.patch.dict(os.environ, {'STUDIO_WORKDIR': str(self.tmp / 'studio')})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_captions_from_carries_highlight(self):
        f, _ = m.studio()
        clip = tiny_clip(self.tmp / 'c.mp4')
        seen = []
        alt = {'question': 'Pick', 'title': 't', 'options': [
            {'option': 'A', 'style': 'quiet', 'label': 'Quiet', 'preview': 'x'},
            {'option': 'B', 'style': 'marker', 'label': 'Marker', 'preview': 'x'}]}

        def fake_finish(raw, out_dir, **kw):
            seen.append(kw['style'])
            out = tiny_clip(Path(out_dir) / 'final.mp4')
            recipe = Path(out_dir) / 'finish.json'
            recipe.write_text(json.dumps({'start_at': kw.get('start_at', 0), 'title': kw.get('title'),
                                          'intro_seconds': kw.get('intro_seconds', 1.6)}))
            return {'output': str(out), 'recipe': str(recipe), 'captions': None}

        with mock.patch.object(f, 'alternatives', return_value=alt), mock.patch.object(f, 'finish', side_effect=fake_finish):
            pid = m.propose_treatments(str(clip), script='a b c')['project_id']
            m.render_preview(pid, 'A')
            m.revise(pid, {'captions_from': 'marker'})
            self.assertEqual(seen[-1]['highlight'], (0, 71, 255))
            self.assertEqual(seen[-1]['highlight_text'], (255, 255, 255))
            m.revise(pid, {'captions_from': 'oxblood'})
            self.assertIsNone(seen[-1]['highlight'])
            self.assertNotIn('highlight_text', seen[-1])


if __name__ == '__main__':
    unittest.main()
