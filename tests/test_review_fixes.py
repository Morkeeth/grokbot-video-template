"""Regression tests for the Codex review of bd09b75. Each one failed on the pre-fix server.

Run against another server copy with TEST_MCP_DIR=/path/to/dir (holding studio_mcp.py and client.py).
"""
import asyncio
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, os.environ.get('TEST_MCP_DIR') or str(ROOT / 'MCP'))
sys.dont_write_bytecode = True
import studio_mcp as m  # noqa: E402
from client import session, call  # noqa: E402

TOOLS = ('propose_treatments', 'render_preview', 'revise', 'finish')
PLACEHOLDERS = {'propose_treatments': {'source': 'check'}, 'render_preview': {'project_id': 'check', 'option': 'A'},
                'revise': {'project_id': 'check', 'edit': {}}, 'finish': {'project_id': 'check'}}


def recipe_of(project_id, version):
    p = json.loads((m.workdir() / project_id / 'project.json').read_text())
    v = next(x for x in p['versions'] if x['version'] == version)
    return v, json.loads(Path(v['recipe']).read_text())


@unittest.skipUnless(os.environ.get('STUDIO_PATH') or os.environ.get('HERMES_STUDIO_PATH') or (Path.home() / 'CODE/hermes-studio-connect').is_dir(), 'needs the Video Studio engine')
class ReviewFixes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix='gbt-fix-'))
        os.environ['STUDIO_WORKDIR'] = str(cls.tmp / 'studio')
        m.studio()
        from connectors import demo
        cls.demo = demo
        cls.clip, _ = demo.sample(cls.tmp / 'input')  # 12 s

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def project(self, source=None):
        r = m.propose_treatments(str(source or self.clip), script=self.demo.LINE, seconds=2, styles=['clean-short', 'brain-rot'])
        self.assertTrue(r['ok'])
        return r['project_id']

    def test_p1_title_only_edit_keeps_mixed_captions(self):
        pid = self.project()
        m.render_preview(pid, 'A', seconds=3)
        m.revise(pid, {'captions_from': 'B'})
        _, mixed = recipe_of(pid, 2)
        m.revise(pid, {'title': 'Second title'})
        _, after = recipe_of(pid, 3)
        for k in ('box', 'text', 'size', 'words', 'y'):
            self.assertEqual(after['style'][k], mixed['style'][k], k)
        self.assertEqual(after['title'], 'Second title')

    def test_p1_revision_keeps_selected_section(self):
        pid = self.project()
        p = m.render_preview(pid, 'A', seconds=4)
        v = m.revise(pid, {'title': 'Only the title'})
        self.assertAlmostEqual(v['probe']['seconds'], p['probe']['seconds'], delta=0.15)
        t = m.revise(pid, {'trim_start': 1})
        self.assertAlmostEqual(t['probe']['seconds'], p['probe']['seconds'] - 1, delta=0.15)  # end stays put

    def test_p2_changed_source_does_not_change_project(self):
        own = self.tmp / 'own.mp4'
        shutil.copyfile(self.clip, own)
        pid = self.project(own)
        subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-y', '-f', 'lavfi', '-i', 'color=red:s=1080x1920:d=3',
                        '-f', 'lavfi', '-i', 'anullsrc=r=48000:cl=stereo', '-t', '3', '-c:v', 'libx264', '-pix_fmt', 'yuv420p',
                        '-c:a', 'aac', str(own)], check=True)
        p = m.render_preview(pid, 'A')
        self.assertGreater(p['probe']['seconds'], 10)  # rendered the 12 s footage it started from, not the 3 s swap
        f = m.finish(pid)
        self.assertEqual(m.sha256(f['source']), f['source_sha256'])

    def test_p2_concurrent_revisions_get_their_own_versions(self):
        pid = self.project()
        m.render_preview(pid, 'A', seconds=3)
        results = []

        def go(title):
            try:
                results.append(m.revise(pid, {'title': title}))
            except Exception as exc:
                results.append({'ok': False, 'error': repr(exc)})
        threads = [threading.Thread(target=go, args=(t,)) for t in ('One', 'Two')]
        [t.start() for t in threads]; [t.join() for t in threads]
        self.assertTrue(all(r.get('ok') for r in results), results)
        self.assertEqual(sorted(r['version'] for r in results), [2, 3])
        self.assertNotEqual(results[0]['preview'], results[1]['preview'])
        project = json.loads((m.workdir() / pid / 'project.json').read_text())
        self.assertEqual(len(project['versions']), 3)
        for v in project['versions']:
            self.assertEqual(m.sha256(v['output']), v['sha256'])


class Readiness(unittest.TestCase):
    """The routine's check calls every tool, and says not ready when rendering cannot work."""

    def check_all(self, env):
        async def go():
            async with session(env) as s:
                return [await call(s, t, {**PLACEHOLDERS[t], 'check_only': True}) for t in TOOLS]
        return asyncio.run(go())

    def test_p2_missing_studio_is_not_ready(self):
        results = self.check_all({'STUDIO_PATH': '/nonexistent/studio-engine'})
        for r in results:
            self.assertIs(r.get('ready'), False, r)
            self.assertTrue(any(x.startswith('Video Studio engine:') for x in r['missing']), r)
            self.assertNotIn('hermes', json.dumps(r).replace('/hermes-studio', '').lower(), r)

    @unittest.skipUnless(os.environ.get('STUDIO_PATH') or os.environ.get('HERMES_STUDIO_PATH') or (Path.home() / 'CODE/hermes-studio-connect').is_dir(), 'needs the Video Studio engine')
    def test_p2_ready_when_environment_works_and_renders_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            results = self.check_all({'STUDIO_WORKDIR': tmp})
            self.assertEqual([r.get('ready') for r in results], [True] * 4, results)
            self.assertEqual(list(Path(tmp).iterdir()), [])


if __name__ == '__main__':
    unittest.main()
