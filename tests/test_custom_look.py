"""Custom caption look: creator sets text/box/size/words/y instead of only picking a preset.

Skip unless the Video Studio engine is present. One real render checks caption pixels.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
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


def recipe_of(project_id, version):
    p = json.loads((m.workdir() / project_id / 'project.json').read_text())
    v = next(x for x in p['versions'] if x['version'] == version)
    return v, json.loads(Path(v['recipe']).read_text())


def version_dirs(project_id):
    d = m.workdir() / project_id
    return sorted(p for p in d.iterdir() if p.is_dir() and p.name.startswith('v'))


def hex_to_rgb(hex_colour):
    """Decode '#rrggbb' in the test itself (not via apply_look / _hex_rgb)."""
    h = hex_colour[1:]
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def frame_rgb_pixels(mp4, at_seconds=1.5):
    """One frame as a list of (r, g, b) via ffmpeg rawvideo rgb24."""
    probe = subprocess.run(
        ['ffprobe', '-v', 'error', '-select_streams', 'v:0',
         '-show_entries', 'stream=width,height', '-of', 'csv=p=0', str(mp4)],
        check=True, capture_output=True, text=True,
    )
    w, h = (int(x) for x in probe.stdout.strip().split(','))
    raw = subprocess.run(
        ['ffmpeg', '-nostdin', '-v', 'error', '-ss', str(at_seconds), '-i', str(mp4),
         '-frames:v', '1', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'],
        check=True, capture_output=True,
    ).stdout
    expected = w * h * 3
    if len(raw) < expected:
        raise AssertionError(f'frame too short: got {len(raw)} want {expected}')
    return [(raw[i], raw[i + 1], raw[i + 2]) for i in range(0, expected, 3)]


def colour_count(pixels, target, tol=15):
    tr, tg, tb = target
    return sum(
        1 for r, g, b in pixels
        if abs(r - tr) <= tol and abs(g - tg) <= tol and abs(b - tb) <= tol
    )


@unittest.skipUnless(HAVE_STUDIO, 'needs the Video Studio engine')
class CustomLook(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix='gbt-look-'))
        os.environ['STUDIO_WORKDIR'] = str(cls.tmp / 'studio')
        m.studio()
        from connectors import demo
        cls.demo = demo
        cls.clip, _ = demo.sample(cls.tmp / 'input')

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def project(self):
        r = m.propose_treatments(
            str(self.clip), script=self.demo.LINE, seconds=2, styles=['clean-short', 'brain-rot']
        )
        self.assertTrue(r['ok'])
        return r['project_id']

    def test_look_renders_requested_caption_colour(self):
        """Real render: caption pixels must contain the requested hex colour."""
        pid = self.project()
        parent = m.render_preview(pid, 'A', seconds=3)
        colour = '#ff3300'
        want = hex_to_rgb(colour)
        r = m.revise(pid, {'look': {'text': colour, 'box': None}}, request='caption colour #ff3300')
        self.assertTrue(r['ok'], r)
        self.assertIn('caption text #ff3300', r['understood'])
        self.assertIn('caption text #ff3300', r['changed'])
        self.assertEqual(r['could_not_change'], [], 'a caption colour note is not a colour grade')
        # The test pattern holds some orange of its own, so the parent frame is the control.
        before = colour_count(frame_rgb_pixels(parent['preview'], at_seconds=1.5), want)
        after = colour_count(frame_rgb_pixels(r['preview'], at_seconds=1.5), want)
        self.assertGreater(after, before + 2000, f'caption colour missing: {before} before, {after} after')

    def test_grade_note_is_still_refused_with_a_look(self):
        pid = self.project()
        m.render_preview(pid, 'A', seconds=2)
        r = m.revise(pid, {'look': {'text': '#ff3300'}}, request='orange captions and a warmer grade')
        self.assertIn('colour grading', r['could_not_change'])

    def test_refuse_unknown_key_renders_nothing(self):
        pid = self.project()
        m.render_preview(pid, 'A', seconds=2)
        before = json.loads((m.workdir() / pid / 'project.json').read_text())
        n_versions = len(before['versions'])
        dirs_before = version_dirs(pid)
        with self.assertRaises(ValueError) as cm:
            m.revise(pid, {'look': {'glow': '#ff3300'}})
        self.assertIn('Unknown look keys', str(cm.exception))
        after = json.loads((m.workdir() / pid / 'project.json').read_text())
        self.assertEqual(len(after['versions']), n_versions)
        self.assertEqual(version_dirs(pid), dirs_before)

    def test_refuse_bad_hex_renders_nothing(self):
        pid = self.project()
        m.render_preview(pid, 'A', seconds=2)
        before = json.loads((m.workdir() / pid / 'project.json').read_text())
        n_versions = len(before['versions'])
        dirs_before = version_dirs(pid)
        with self.assertRaises(ValueError) as cm:
            m.revise(pid, {'look': {'text': 'ff3300'}})
        self.assertIn('hex colour', str(cm.exception))
        after = json.loads((m.workdir() / pid / 'project.json').read_text())
        self.assertEqual(len(after['versions']), n_versions)
        self.assertEqual(version_dirs(pid), dirs_before)

    def test_refuse_out_of_range_renders_nothing(self):
        pid = self.project()
        m.render_preview(pid, 'A', seconds=2)
        before = json.loads((m.workdir() / pid / 'project.json').read_text())
        n_versions = len(before['versions'])
        dirs_before = version_dirs(pid)
        cases = (
            {'size': 10},
            {'words': 9},
            {'y': 1.5},
        )
        for look in cases:
            with self.subTest(look=look):
                with self.assertRaises(ValueError):
                    m.revise(pid, {'look': look})
                after = json.loads((m.workdir() / pid / 'project.json').read_text())
                self.assertEqual(len(after['versions']), n_versions)
                self.assertEqual(version_dirs(pid), dirs_before)

    def test_look_persists_across_title_only_revision(self):
        """After JSON round trip, custom text colour stays; intro colours unchanged by look alone."""
        pid = self.project()
        m.render_preview(pid, 'A', seconds=3)
        v0, recipe0 = recipe_of(pid, 1)
        intro_dark = recipe0['style'].get('intro_dark')
        intro_light = recipe0['style'].get('intro_light')
        colour = '#ff3300'
        want = hex_to_rgb(colour)
        r1 = m.revise(pid, {'look': {'text': colour}}, request='orange captions')
        self.assertTrue(r1['ok'], r1)
        v1, recipe1 = recipe_of(pid, 2)
        text1 = recipe1['style']['text']
        self.assertEqual(list(text1), list(want))
        self.assertEqual(recipe1['style'].get('intro_dark'), intro_dark)
        self.assertEqual(recipe1['style'].get('intro_light'), intro_light)
        eff1 = v1.get('effective_style') or {}
        self.assertEqual(list(eff1.get('text', [])), list(want))
        self.assertEqual(eff1.get('intro_dark'), intro_dark)
        self.assertEqual(eff1.get('intro_light'), intro_light)

        r2 = m.revise(pid, {'title': 'Only the title'})
        self.assertTrue(r2['ok'], r2)
        v2, recipe2 = recipe_of(pid, 3)
        self.assertEqual(list(recipe2['style']['text']), list(want))
        self.assertEqual(recipe2['title'], 'Only the title')
        self.assertEqual(recipe2['style'].get('intro_dark'), intro_dark)
        self.assertEqual(recipe2['style'].get('intro_light'), intro_light)
        eff2 = v2.get('effective_style') or {}
        self.assertEqual(list(eff2.get('text', [])), list(want))


if __name__ == '__main__':
    unittest.main()
