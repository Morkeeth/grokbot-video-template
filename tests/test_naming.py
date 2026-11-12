"""What a creator reads never names the engine's repo: STUDIO_PATH, public style names, the fallback title."""
import asyncio
import json
import os
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
from client import session, call  # noqa: E402

HAVE_STUDIO = bool(os.environ.get('STUDIO_PATH') or os.environ.get('HERMES_STUDIO_PATH')
                   or (Path.home() / 'CODE/hermes-studio-connect').is_dir())


def creator_text(obj):
    """Everything a creator could read, minus file paths (folder names are the engine's own)."""
    s = json.dumps(obj)
    return ' '.join(w for w in s.replace('"', ' ').split() if '/' not in w).lower()


class StudioPath(unittest.TestCase):
    def fake(self, tmp, name):
        p = Path(tmp) / name / 'connectors'
        p.mkdir(parents=True)
        (p / 'finish.py').write_text('')
        return p.parent

    def test_studio_path_wins_over_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            a, b = self.fake(tmp, 'new'), self.fake(tmp, 'old')
            with mock.patch.dict(os.environ, {'STUDIO_PATH': str(a), 'HERMES_STUDIO_PATH': str(b)}):
                self.assertEqual(m.studio_path(), a.resolve())

    def test_hermes_studio_path_still_works(self):
        with tempfile.TemporaryDirectory() as tmp:
            b = self.fake(tmp, 'old')
            env = {k: v for k, v in os.environ.items() if k != 'STUDIO_PATH'}
            env['HERMES_STUDIO_PATH'] = str(b)
            with mock.patch.dict(os.environ, env, clear=True):
                self.assertEqual(m.studio_path(), b.resolve())

    def test_missing_engine_message_names_studio_path(self):
        with mock.patch.dict(os.environ, {'STUDIO_PATH': '/nonexistent/engine'}):
            with self.assertRaises(RuntimeError) as e:
                m.studio_path()
        self.assertIn('Video Studio engine not found', str(e.exception))
        self.assertIn('STUDIO_PATH', str(e.exception))


@unittest.skipUnless(HAVE_STUDIO, 'needs the Video Studio engine')
class PublicNames(unittest.TestCase):
    def test_silent_clip_uses_neutral_title_and_public_style_names(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            clip = tmp / 'silent.mp4'
            subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-y', '-f', 'lavfi', '-i', 'color=blue:s=108x192:d=2',
                            '-c:v', 'libx264', '-pix_fmt', 'yuv420p', str(clip)], check=True)

            async def go():
                async with session({'STUDIO_WORKDIR': str(tmp / 'studio')}) as s:
                    r = await call(s, 'propose_treatments', {'source': str(clip), 'seconds': 2,
                                                             'styles': ['clean-short', 'hermes-dither']})
                    self.assertTrue(r['ok'], r)
                    self.assertEqual([t['style'] for t in r['treatments']], ['clean-short', 'dither'])
                    self.assertEqual(r['question'], 'Pick a style: A Clean short, B Dither')
                    p = await call(s, 'render_preview', {'project_id': r['project_id'], 'option': 'dither', 'seconds': 2})
                    self.assertTrue(p['ok'], p)
                    v = await call(s, 'revise', {'project_id': r['project_id'], 'edit': {'captions_from': 'B', 'punchier': True}})
                    self.assertTrue(v['ok'], v)
                    bad = await call(s, 'render_preview', {'project_id': r['project_id'], 'option': 'nope'})
                    self.assertFalse(bad['ok'])
                    for out in (r, p, v, bad):
                        self.assertNotIn('hermes', creator_text(out), out)
                    proj = json.loads((tmp / 'studio' / r['project_id'] / 'project.json').read_text())
                    recipe = json.loads(Path(proj['versions'][-1]['recipe']).read_text())
                    self.assertEqual(recipe['title'], m.FALLBACK_TITLE)
            asyncio.run(go())


if __name__ == '__main__':
    unittest.main()
