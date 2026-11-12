"""MCP tool tests, driven through a real stdio MCP client session (what a host sees)."""
import asyncio
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, os.environ.get('TEST_MCP_DIR') or str(ROOT / 'MCP'))
sys.dont_write_bytecode = True
from client import session, call  # noqa: E402
import studio_mcp  # noqa: E402

TOOLS = {'propose_treatments', 'render_preview', 'revise', 'finish'}


def run(coro):
    return asyncio.run(coro)


class Schema(unittest.TestCase):
    """No renders: tool names, required inputs and the revise edit contract."""

    def test_schemas(self):
        async def go():
            async with session() as s:
                return {t.name: t.inputSchema for t in (await s.list_tools()).tools}
        tools = run(go())
        self.assertEqual(set(tools), TOOLS)
        self.assertEqual(set(tools['propose_treatments']['required']), {'source'})
        self.assertEqual(set(tools['render_preview']['required']), {'project_id', 'option'})
        self.assertEqual(set(tools['revise']['required']), {'project_id', 'edit'})
        self.assertEqual(set(tools['finish']['required']), {'project_id'})
        blob = json.dumps(tools['revise'])
        for field in studio_mcp.REVISE_FIELDS:
            self.assertIn(field, blob)
        self.assertIn('additionalProperties', blob)  # unknown edit fields are rejected, not ignored

    def test_unknown_edit_field_rejected(self):
        async def go():
            async with session() as s:
                return await s.call_tool('revise', {'project_id': 'p-0000000000', 'edit': {'colour_grade': 'warm'}})
        res = run(go())
        self.assertTrue(res.isError or 'error' in res.content[0].text.lower())

    def test_bad_project_id_is_an_error_not_success(self):
        async def go():
            async with session() as s:
                return await call(s, 'finish', {'project_id': '../../etc'})
        r = run(go())
        self.assertFalse(r['ok'])


@unittest.skipUnless(os.environ.get('STUDIO_PATH') or os.environ.get('HERMES_STUDIO_PATH') or (Path.home() / 'CODE/hermes-studio-connect').is_dir(), 'needs the Video Studio engine')
class RoundTrip(unittest.TestCase):
    """One full round trip on a tiny generated clip: propose, preview, revise, finish."""

    def test_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            studio_mcp.studio()
            from connectors import demo
            clip, _ = demo.sample(tmp / 'input')

            async def go():
                async with session({'STUDIO_WORKDIR': str(tmp / 'studio')}) as s:
                    r = await call(s, 'propose_treatments', {'source': str(clip), 'script': demo.LINE, 'seconds': 3, 'styles': ['clean-short', 'hermes-dither']})
                    self.assertTrue(r['ok'], r)
                    self.assertEqual([t['option'] for t in r['treatments']], ['A', 'B'])
                    pid = r['project_id']
                    p = await call(s, 'render_preview', {'project_id': pid, 'option': 'B', 'seconds': 4})
                    self.assertTrue(p['ok'], p)
                    v = await call(s, 'revise', {'project_id': pid, 'request': 'clean look and a colour grade',
                                                 'edit': {'style': 'A', 'quieter_music': True}})
                    self.assertTrue(v['ok'], v)
                    self.assertEqual(v['version'], 2)
                    self.assertIn('style clean-short', v['changed'])
                    self.assertTrue(any('quieter music' in c for c in v['could_not_change']))
                    self.assertIn('colour grading', v['could_not_change'])
                    self.assertTrue(Path(v['previous_version_kept']).is_file())
                    self.assertNotEqual(v['sha256'], p['sha256'])
                    f = await call(s, 'finish', {'project_id': pid})
                    self.assertTrue(f['ok'], f)
                    self.assertTrue(all(f['checks'].values()))
                    self.assertEqual(len(f['history']), 2)
                    again = await call(s, 'finish', {'project_id': pid})
                    self.assertFalse(again['ok'])  # handoffs are never overwritten
            run(go())


if __name__ == '__main__':
    unittest.main()
