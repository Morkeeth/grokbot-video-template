"""Regression tests for the Codex re-review of 1cc8f26. No full renders: a tiny clip or a mocked renderer.

Both findings fail on the 1cc8f26 server (TEST_MCP_DIR pointing at a copy of it).
"""
import asyncio
import json
import os
import shutil
import stat
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
from client import session  # noqa: E402

HAVE_STUDIO = bool(os.environ.get('STUDIO_PATH') or os.environ.get('HERMES_STUDIO_PATH') or (Path.home() / 'CODE/hermes-studio-connect').is_dir())


def tiny_clip(path, audio=True):
    """0.5 s, 108x192: cheap enough to need no suite lock."""
    a = ['-f', 'lavfi', '-i', 'sine=f=440:d=0.5'] if audio else []
    subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-y', '-f', 'lavfi', '-i', 'color=blue:s=108x192:d=0.5', *a,
                    '-t', '0.5', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', *(['-c:a', 'aac'] if audio else []), str(path)], check=True)
    return path


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix='gbt-rr-'))
        self.env = mock.patch.dict(os.environ, {'STUDIO_WORKDIR': str(self.tmp / 'studio')})
        self.env.start()
        os.environ.pop('STUDIO_WHISPER_MODEL', None)

    def tearDown(self):
        self.env.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)


class HandoffRecipe(Base):
    def test_handoff_recipe_keeps_selected_end(self):
        """Preview seconds=4 then trim_start=1: the handed-off recipe must bound the replay to 3 s."""
        pid = 'p-0123456789'
        d = m.workdir() / pid
        (d / 'source').mkdir(parents=True)
        src = tiny_clip(d / 'source' / 'clip.mp4')
        out = tiny_clip(self.tmp / 'final.mp4')
        recipe = self.tmp / 'finish.json'
        recipe.write_text(json.dumps({'source': str(src), 'start_at': 1.0, 'title': 'T', 'style': 'clean-short'}))
        version = {'version': 2, 'kind': 'revision', 'note': 'trim', 'style': 'clean-short', 'window': {'start': 1.0, 'end': 4.0},
                   'output': str(out), 'sha256': m.sha256(out), 'recipe': str(recipe), 'captions': None,
                   'changed': [], 'could_not_change': []}
        (d / 'project.json').write_text(json.dumps({'id': pid, 'source': str(src), 'source_sha256': m.sha256(src),
                                                    'treatments': [], 'versions': [version]}))
        f = m.finish(pid)
        handed = json.loads(Path(f['files']['recipe.json']).read_text())
        self.assertEqual(handed.get('max_seconds'), 3.0)
        self.assertEqual(handed.get('window'), {'start': 1.0, 'end': 4.0})
        self.assertEqual(handed.get('start_at'), 1.0)


@unittest.skipUnless(HAVE_STUDIO, 'needs the Video Studio engine')
class SpeechModel(Base):
    def test_schema_accepts_model(self):
        async def go():
            async with session() as s:
                return {t.name: t.inputSchema for t in (await s.list_tools()).tools}
        self.assertIn('model', run(go())['propose_treatments']['properties'])

    def test_no_script_no_model_says_how_to_fix_before_rendering(self):
        clip = tiny_clip(self.tmp / 'talk.mp4')
        with self.assertRaises(ValueError) as cm:
            m.propose_treatments(str(clip))
        self.assertIn('script', str(cm.exception))
        self.assertIn('STUDIO_WHISPER_MODEL', str(cm.exception))
        self.assertFalse(any((p / 'treatments').exists() for p in m.workdir().iterdir()))

    def test_model_transcribes_once_at_intake(self):
        clip = tiny_clip(self.tmp / 'talk.mp4')
        model = self.tmp / 'ggml-tiny.bin'; model.write_bytes(b'x')
        bindir = self.tmp / 'bin'; bindir.mkdir()
        fake = bindir / 'whisper-cli'; fake.write_text('#!/bin/sh\nexit 0\n'); fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
        f, _ = m.studio()
        words = [{'text': 'hello', 'start': 0.1, 'end': 0.3}]
        alt = {'question': 'Pick', 'title': 'hello', 'options': [{'option': 'A', 'style': 'clean-short', 'label': 'Clean short', 'preview': 'x'},
                                                                  {'option': 'B', 'style': 'brain-rot', 'label': 'Brain rot', 'preview': 'y'}]}
        with mock.patch.dict(os.environ, {'PATH': f"{bindir}:{os.environ['PATH']}"}), \
                mock.patch.object(f, 'transcribe_words', return_value=words) as tw, \
                mock.patch.object(f, 'alternatives', return_value=alt) as al:
            r = m.propose_treatments(str(clip), model=str(model))
        self.assertTrue(r['ok'])
        tw.assert_called_once()
        self.assertEqual(al.call_args.kwargs['words'], words)
        project = json.loads((m.workdir() / r['project_id'] / 'project.json').read_text())
        self.assertEqual(project['words'], words)  # later versions reuse these; no model needed again

    def test_readiness_reports_caption_route_and_bad_model(self):
        self.assertIn('script only', m.readiness('x')['checks']['captions_from'])
        with mock.patch.dict(os.environ, {'STUDIO_WHISPER_MODEL': str(self.tmp / 'missing.bin')}):
            r = m.readiness('x')
        self.assertFalse(r['ready'])
        self.assertTrue(any('speech model' in x for x in r['missing']))


def run(coro):
    return asyncio.run(coro)


if __name__ == '__main__':
    unittest.main()


@unittest.skipUnless(HAVE_STUDIO, 'needs the Video Studio engine')
class PresetParity(Base):
    """A picked preset must render with the same caption look as the treatment the creator saw (no inherited highlight)."""

    def test_every_preset_renders_as_its_name(self):
        f, s = m.studio()
        clip = tiny_clip(self.tmp / 'c.mp4')
        alt = {'question': 'Pick', 'title': 't', 'options': [{'option': 'A', 'style': n, 'label': n, 'preview': 'x'} for n in s.STYLES][:3]}
        styles_seen = []

        def fake_finish(raw, out_dir, **kw):
            styles_seen.append(kw['style'])
            out = tiny_clip(Path(out_dir) / 'final.mp4')
            r = Path(out_dir) / 'finish.json'; r.write_text(json.dumps({'start_at': kw.get('start_at', 0), 'title': kw.get('title'), 'intro_seconds': kw.get('intro_seconds', 1.6)}))
            return {'output': str(out), 'recipe': str(r), 'captions': None}
        with mock.patch.object(f, 'alternatives', return_value=alt), mock.patch.object(f, 'finish', side_effect=fake_finish):
            pid = m.propose_treatments(str(clip), script='a b c')['project_id']
            for name in s.STYLES:
                m.render_preview(pid, name)
                m.revise(pid, {'style': name})
        for passed in styles_seen:
            name = next(n for n in s.STYLES if all(passed.get(k) == v for k, v in s.STYLES[n].items()))
            self.assertEqual(s.get(passed).get('highlight'), s.get(name).get('highlight'), name)
