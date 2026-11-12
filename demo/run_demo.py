"""First five minutes: a generated sample clip, three treatments, a pick, one revision, an MP4 out.

No keys, no network, no paid call, no private footage. The sample is a colour test pattern with the
machine's own text-to-speech voice, built by Hermes Studio's connectors.demo.sample. The voice
and captions say this template's line, not Hermes Studio's own. Every tool call goes
through the MCP server over stdio, the same way Grok Bot or any MCP host would call it.

    HERMES_STUDIO_PATH=/path/to/hermes-studio python3 demo/run_demo.py OUT_DIR
"""
import asyncio
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'MCP'))
sys.dont_write_bytecode = True
import studio_mcp  # noqa: E402
from client import session, call  # noqa: E402

LINE = 'Welcome to the Grok Bot Video Studio. Send raw footage, pick a style, and get a finished short back.'


async def main(out):
    out = Path(out).expanduser().resolve()
    if out.exists() and any(out.iterdir()):
        raise SystemExit(f'{out} is not empty; pick a new folder (runs never overwrite)')
    out.mkdir(parents=True, exist_ok=True)
    studio_mcp.studio()
    from connectors import demo  # Hermes Studio, read-only
    demo.LINE = LINE  # the sample voice reads this module global at call time; Hermes Studio files are unchanged
    clip, voiced = demo.sample(out / 'input')
    env = {'STUDIO_WORKDIR': str(out / 'studio')}
    log, t0 = [], time.time()
    async with session(env) as s:
        tools = sorted(t.name for t in (await s.list_tools()).tools)
        log.append({'step': 'list_tools', 'tools': tools})
        r = await call(s, 'propose_treatments', {'source': str(clip), 'script': LINE, 'seconds': 5})
        assert r.get('ok'), r
        log.append({'step': 'propose_treatments', 'question': r['question'], 'previews': [t['preview'] for t in r['treatments']]})
        pid = r['project_id']
        p = await call(s, 'render_preview', {'project_id': pid, 'option': 'C'})
        assert p.get('ok'), p
        log.append({'step': 'render_preview', 'creator': 'C', 'version': p['version'], 'probe': p['probe']})
        note = 'Keep it but use the clean look, tighten the intro, and lower the music.'
        v = await call(s, 'revise', {'project_id': pid, 'request': note,
                                     'edit': {'style': 'A', 'trim_start': 1.5, 'punchier': True, 'quieter_music': True}})
        assert v.get('ok'), v
        log.append({'step': 'revise', 'creator': note, **{k: v[k] for k in ('version', 'understood', 'changed', 'could_not_change', 'previous_version_kept', 'probe')}})
        f = await call(s, 'finish', {'project_id': pid})
        assert f.get('ok'), f
        log.append({'step': 'finish', 'folder': f['folder'], 'mp4': f['files']['final.mp4'], 'sha256': f['sha256'], 'checks': f['checks']})
    summary = {'ok': True, 'seconds_total': round(time.time() - t0, 1), 'sample': str(clip),
               'voice': 'system text-to-speech' if voiced else 'silent sample (no TTS found)',
               'mp4': f['files']['final.mp4'], 'sha256': f['sha256'], 'steps': log,
               'label': 'local test artifact from a generated test pattern; not render_gate certified'}
    (out / 'demo-run.json').write_text(json.dumps(summary, indent=1))
    print(json.dumps(summary, indent=1))


if __name__ == '__main__':
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else 'demo-out'))
