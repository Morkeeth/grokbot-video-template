"""Video Studio MCP server for Grok Bot: four tools over the Video Studio engine.

Tools: propose_treatments, render_preview, revise, finish.
The Video Studio engine (the public repo github.com/Morkeeth/hermes-studio) is imported read-only
from STUDIO_PATH (HERMES_STUDIO_PATH still works as a fallback). Nothing is installed,
downloaded, uploaded, published or paid for. Every render goes to a new version folder,
so earlier versions are never overwritten.
"""
import contextlib
import fcntl
import hashlib
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.dont_write_bytecode = True  # never write caches into the Studio checkout

DEFAULT_STUDIO = Path.home() / 'CODE' / 'hermes-studio-connect'
REVISE_FIELDS = ('style', 'captions_from', 'trim_start', 'punchier', 'title', 'quieter_music')
NOT_SUPPORTED_WORDS = {
    'colour': 'colour grading', 'color': 'colour grading', 'grade': 'colour grading',
    'b-roll': 'new B-roll from a description', 'broll': 'new B-roll from a description',
    'zoom': 'punch-in zooms', 'transition': 'transitions between shots', 'voice': 'voice changes',
    'generate': 'generated shots (paid; needs a quote and the owner\'s explicit yes)',
    'upload': 'uploading or posting', 'post': 'uploading or posting', 'publish': 'uploading or posting',
}
# The engine's own style ids and labels carry its repo name. Creators see these public ones instead.
PUBLIC_STYLE = {'hermes-dither': 'dither'}
ENGINE_STYLE = {v: k for k, v in PUBLIC_STYLE.items()}
PUBLIC_LABEL = {'hermes-dither': 'Dither'}
FALLBACK_TITLE = 'VIDEO STUDIO'  # the engine's own fallback title names its repo; a clip with no words gets this


def engine_style(name):
    """Public or engine style id in, engine style id out. Unknown names are refused in public terms."""
    n = str(name).strip()
    n = ENGINE_STYLE.get(n, n)
    return n


def public_style(name):
    return PUBLIC_STYLE.get(name, name)


def style_names(s):
    return sorted(public_style(n) for n in s.STYLES)


def style_label(s, name):
    return PUBLIC_LABEL.get(name) or s.get(name)['label']


def resolve_title(f, title, words):
    """The title the engine would burn in, minus its own fallback, which names its repo."""
    return title or (f.hook_title(words) if words else '') or FALLBACK_TITLE


def check_style(s, name):
    n = engine_style(name)
    if n not in s.STYLES:
        raise ValueError(f'Unknown style {name}; choose from {style_names(s)}')
    return n


def studio_path():
    p = Path(os.environ.get('STUDIO_PATH') or os.environ.get('HERMES_STUDIO_PATH') or DEFAULT_STUDIO).expanduser().resolve()
    if not (p / 'connectors' / 'finish.py').is_file():
        raise RuntimeError(f'Video Studio engine not found at {p}; set STUDIO_PATH to a clone of github.com/Morkeeth/hermes-studio')
    return p


def studio():
    root = str(studio_path())
    if root not in sys.path:
        sys.path.insert(0, root)
    from connectors import finish as f, styles as s  # noqa: E402  (read-only import)
    return f, s


def workdir():
    p = Path(os.environ.get('STUDIO_WORKDIR') or (Path.home() / 'GrokbotStudio')).expanduser().resolve()
    p.mkdir(parents=True, exist_ok=True)
    return p


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def probe(path):
    out = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'stream=codec_type,width,height,r_frame_rate',
                          '-show_entries', 'format=duration', '-of', 'json', str(path)],
                         capture_output=True, text=True, check=True).stdout
    data = json.loads(out)
    v = next((s for s in data['streams'] if s['codec_type'] == 'video'), {})
    return {'seconds': round(float(data['format']['duration']), 2), 'width': v.get('width'), 'height': v.get('height'),
            'fps': v.get('r_frame_rate'), 'audio': any(s['codec_type'] == 'audio' for s in data['streams'])}


# ---------- project store ----------

def _project_dir(project_id):
    if not re.fullmatch(r'p-[0-9a-f]{10}', str(project_id)):
        raise ValueError('Unknown project id; call propose_treatments first')
    d = workdir() / project_id
    if not (d / 'project.json').is_file():
        raise ValueError(f'No project {project_id} in this studio')
    return d


@contextlib.contextmanager
def _locked(project_id):
    """One call at a time per project: load, render and save happen under one exclusive lock."""
    d = _project_dir(project_id)
    with open(d / '.lock', 'a') as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        try:
            yield d, json.loads((d / 'project.json').read_text())
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


def _save(d, project):
    project['updated_at'] = time.strftime('%Y-%m-%dT%H:%M:%S%z')
    fd, tmp = tempfile.mkstemp(dir=d, prefix='project.', suffix='.tmp')
    with os.fdopen(fd, 'w') as fh:
        fh.write(json.dumps(project, indent=1))
    os.replace(tmp, d / 'project.json')


def _source(project):
    """The project's frozen source copy, checked against the hash recorded at intake."""
    src = Path(project['source'])
    if not src.is_file() or sha256(src) != project['source_sha256']:
        raise ValueError('The project source no longer matches the footage it was started from; start a new project')
    return src


def _version_dir(d, n):
    """A fresh folder per version. mkdir fails rather than reuse a folder another call made."""
    out = d / f'v{n}-{secrets.token_hex(3)}'
    out.mkdir()
    return out


def _words(script, seconds):
    """Even timing for a known script, so a run works without a local speech model."""
    ws = str(script).split()
    if not ws:
        return []
    step = max(0.2, (seconds - 1.0) / len(ws))
    return [{'text': w, 'start': round(0.5 + i * step, 3), 'end': round(0.5 + (i + 1) * step, 3)} for i, w in enumerate(ws)]


def _version(d, project, kind, result, note, style_name, effective_style, window, changed=None, could_not=None, parent=None):
    n = len(project['versions']) + 1
    entry = {'version': n, 'kind': kind, 'note': note, 'style': style_name, 'effective_style': effective_style,
             'window': window, 'parent': parent,
             'output': result['output'], 'sha256': sha256(result['output']), 'recipe': result.get('recipe'),
             'captions': result.get('captions'), 'probe': probe(result['output']),
             'changed': changed or [], 'could_not_change': could_not or []}
    project['versions'].append(entry)
    _save(d, project)
    return entry


def _preset(s, name):
    """A preset as a full dict that renders the same as the preset name.

    The engine merges a style dict over its dither style, so keys a preset leaves out (its caption highlight)
    would be inherited. Pin them off explicitly.
    """
    n = check_style(s, name)
    st = dict(s.get(n))
    st.setdefault('highlight', None)
    st['label'] = style_label(s, n)  # the engine writes this dict into recipe.json, which the creator gets
    return st


def readiness(tool):
    """Read-only: can this connector render right now? Never renders, installs or spends."""
    checks, missing = {}, []
    try:
        studio(); checks['studio_engine'] = str(studio_path())
    except Exception as exc:
        checks['studio_engine'] = False; missing.append(f'Video Studio engine: {exc}')
    for exe in ('ffmpeg', 'ffprobe'):
        checks[exe] = bool(shutil.which(exe))
        if not checks[exe]:
            missing.append(f'{exe} not on PATH')
    try:
        w = workdir()
        with tempfile.NamedTemporaryFile(dir=w, prefix='.check-'):
            pass
        checks['workdir_writable'] = str(w)
    except Exception as exc:
        checks['workdir_writable'] = False; missing.append(f'work folder: {exc}')
    try:
        mdl = speech_model()
        checks['captions_from'] = f'local whisper.cpp ({mdl})' if mdl else 'script only: pass the spoken words as `script`'
    except Exception as exc:
        checks['captions_from'] = False; missing.append(f'speech model: {exc}')
    return {'ok': not missing, 'tool': tool, 'ready': not missing, 'checks': checks, 'missing': missing,
            'scope': 'Environment check only; no render was made'}


# ---------- tools ----------

def speech_model(model=None):
    """The local whisper.cpp model to use, if any: the call's `model`, else STUDIO_WHISPER_MODEL."""
    m = model or os.environ.get('STUDIO_WHISPER_MODEL')
    if not m:
        return None
    p = Path(m).expanduser()
    if not p.is_file():
        raise ValueError(f'Speech model not found: {p}')
    if not (shutil.which('whisper-cli') or shutil.which('whisper-cpp')):
        raise ValueError('A speech model is set but whisper-cli is not on PATH')
    return p


def propose_treatments(source, title='', script='', seconds=6.0, styles=None, model=None):
    """Render the opening of one clip in 2-3 visibly different styles, as the first creative proposal."""
    f, s = studio()
    src = Path(source).expanduser().resolve(strict=True)
    if not src.is_file():
        raise ValueError('source must be a local video file')
    styles = list(styles or ['clean-short', 'brain-rot', 'dither'])
    if not 2 <= len(styles) <= 3:
        raise ValueError('Ask for two or three treatments')
    styles = [check_style(s, name) for name in styles]
    seconds = float(seconds)
    if not 2 <= seconds <= 30:
        raise ValueError('seconds must be between 2 and 30')
    src_sha = sha256(src)
    pid = 'p-' + hashlib.sha256(f'{src_sha}{time.time_ns()}{secrets.token_hex(4)}'.encode()).hexdigest()[:10]
    d = workdir() / pid
    d.mkdir()
    # Freeze an owned, read-only copy: later renders and the handoff use this, never the outside path.
    (d / 'source').mkdir()
    frozen = d / 'source' / f'{src_sha[:16]}{src.suffix.lower()}'
    shutil.copyfile(src, frozen)
    os.chmod(frozen, 0o444)
    if sha256(frozen) != src_sha:
        raise ValueError('The source changed while it was being copied; try again')
    if script:
        words, words_from = _words(script, probe(frozen)['seconds']), 'script, even timing'
    elif not probe(frozen)['audio']:
        words, words_from = [], 'no audio'
    else:
        mdl = speech_model(model)
        if mdl is None:
            raise ValueError('No words for the captions: pass `script` (the spoken words), or set `model` / STUDIO_WHISPER_MODEL to a local whisper.cpp model')
        with tempfile.TemporaryDirectory() as tmp:
            words = f.transcribe_words(frozen, mdl, tmp)  # once, at intake; every later version reuses these words
        words_from = f'local whisper.cpp ({mdl.name})'
    alt = f.alternatives(frozen, d / 'treatments', title=resolve_title(f, title, words),
                         words=words, styles=tuple(styles), seconds=seconds)
    for o in alt['options']:
        o['label'] = style_label(s, o['style'])
    note = alt.get('editor_note')
    if isinstance(note, dict) and note.get('pick'):
        note = {**note, 'pick': public_style(note['pick'])}
    question = 'Pick a style: ' + ', '.join(f"{o['option']} {o['label']}" for o in alt['options'])
    project = {'id': pid, 'source': str(frozen), 'source_original': str(src), 'source_sha256': src_sha,
               'title': alt.get('title') or title, 'words': words, 'words_from': words_from, 'treatments': alt['options'],
               'editor_note': note, 'versions': [], 'created_at': time.strftime('%Y-%m-%dT%H:%M:%S%z')}
    _save(d, project)
    return {'ok': True, 'project_id': pid, 'question': question,
            'treatments': [{'option': o['option'], 'style': public_style(o['style']), 'label': o['label'], 'preview': o['preview']}
                           for o in alt['options']],
            'editor_note': note, 'words_from': words_from,
            'next': 'Show the previews. Ask the creator to pick a letter, then call render_preview.'}


def render_preview(project_id, option, seconds=None):
    """Render the picked treatment over the whole clip (or the first `seconds`) as a new version."""
    f, s = studio()
    with _locked(project_id) as (d, project):
        src = _source(project)
        letters = {t['option']: t['style'] for t in project['treatments']}
        style = check_style(s, letters.get(str(option).strip().upper(), str(option).strip()))
        st = _preset(s, style)
        if seconds is not None and float(seconds) <= 0:
            raise ValueError('seconds must be positive')
        window = {'start': 0.0, 'end': float(seconds) if seconds else None}
        out = _version_dir(d, len(project['versions']) + 1)
        r = f.finish(src, out, title=resolve_title(f, project.get('title'), project.get('words')),
                     words=project.get('words'), style=st, max_seconds=window['end'])
        v = _version(d, project, 'preview', r, f'picked {option} ({public_style(style)})', style, st, window)
    return {'ok': True, 'project_id': project_id, 'version': v['version'], 'preview': v['output'], 'sha256': v['sha256'],
            'probe': v['probe'], 'window': window, 'next': 'Show the preview. Ask what should change, then call revise.'}


def revise(project_id, edit, request=''):
    """Apply one conversational revision as a new version. Reports understood, changed and could-not-change."""
    f, s = studio()
    if not isinstance(edit, dict) or not edit:
        raise ValueError('edit must name at least one of: ' + ', '.join(REVISE_FIELDS))
    unknown = set(edit) - set(REVISE_FIELDS)
    if unknown:
        raise ValueError(f'Unsupported edit fields {sorted(unknown)}; supported: ' + ', '.join(REVISE_FIELDS))
    with _locked(project_id) as (d, project):
        if not project['versions']:
            raise ValueError('Render a preview first (render_preview)')
        src = _source(project)
        parent = project['versions'][-1]
        recipe = json.loads(Path(parent['recipe']).read_text())
        letters = {t['option']: t['style'] for t in project['treatments']}

        def pick(v):
            v = str(v).strip()
            return check_style(s, letters.get(v.upper(), v) if len(v) == 1 else v)

        understood, changed, could_not = [], [], []
        if 'style' in edit:
            base = pick(edit['style'])
            st = _preset(s, base)
            understood.append(f'switch to {public_style(base)}'); changed.append(f'style {public_style(base)}')
        else:
            # Keep everything the creator already chose (including mixed captions); change only what was asked.
            base = parent['style']
            st = dict(parent.get('effective_style') or _preset(s, base))
        if 'captions_from' in edit:
            cap_name = pick(edit['captions_from'])
            cap = s.get(cap_name)
            st.update({k: cap[k] for k in ('box', 'text', 'size', 'words', 'y')})
            understood.append(f"captions in the {public_style(cap_name)} look"); changed.append(f"captions from {public_style(cap_name)}")
        window = dict(parent.get('window') or {'start': float(recipe.get('start_at') or 0), 'end': None})
        if edit.get('trim_start'):
            t = float(edit['trim_start'])
            if not 0 < t <= 30:
                raise ValueError('trim_start is seconds to cut from the opening, 0 to 30')
            window['start'] += t
            understood.append(f'tighter opening, cut {t:g} s'); changed.append(f'opening tightened by {t:g} s')
        # The end of the chosen section stays where the creator put it.
        max_seconds = None
        if window.get('end') is not None:
            max_seconds = window['end'] - window['start']
            if max_seconds <= 0.5:
                raise ValueError('That trim would remove the whole selected section')
        intro = float(recipe.get('intro_seconds') or 1.6)
        if edit.get('punchier'):
            intro = max(0.6, intro - 0.6)
            understood.append('punchier intro'); changed.append(f'intro shortened to {intro:.1f} s')
        title = resolve_title(f, str(edit.get('title') or recipe.get('title') or ''), project.get('words'))
        if edit.get('title'):
            understood.append(f'new title "{title}"'); changed.append('new title')
        music = recipe.get('music')
        music_db = float(recipe.get('music_db', -20))
        if edit.get('quieter_music'):
            understood.append('quieter music')
            if music:
                music_db -= 6; changed.append(f'music bed 6 dB quieter ({music_db:.0f} dB)')
            else:
                could_not.append('quieter music: this version has no separate music bed; the voice track was left as is')
        low = str(request).lower()
        for word, what in NOT_SUPPORTED_WORDS.items():
            if re.search(rf'\b{re.escape(word)}', low) and what not in could_not:
                could_not.append(what)
        words = project.get('words') if project.get('words') is not None else recipe.get('words')
        out = _version_dir(d, len(project['versions']) + 1)
        r = f.finish(src, out, title=title, words=words, style=st, intro_seconds=intro, start_at=window['start'],
                     max_seconds=max_seconds, music=music, music_db=music_db)
        v = _version(d, project, 'revision', r, request or 'revision', base, st, window, changed, could_not,
                     parent=parent['version'])
    return {'ok': True, 'project_id': project_id, 'version': v['version'], 'previous_version_kept': parent['output'],
            'understood': understood, 'changed': changed, 'could_not_change': could_not,
            'preview': v['output'], 'sha256': v['sha256'], 'probe': v['probe'], 'window': window,
            'next': 'Show what was understood, what changed and what could not. Ask for the next note, or call finish.'}


def finish(project_id, version=None):
    """Hand off one version: MP4, captions and the re-runnable recipe in a final folder. Never publishes."""
    with _locked(project_id) as (d, project):
        if not project['versions']:
            raise ValueError('Nothing rendered yet')
        _source(project)
        v = project['versions'][-1] if version is None else next((x for x in project['versions'] if x['version'] == int(version)), None)
        if v is None:
            raise ValueError(f'No version {version}')
        if sha256(v['output']) != v['sha256']:
            raise ValueError('That version changed on disk after it was rendered; re-render it')
        out = d / f"final-v{v['version']}"
        if out.exists():
            raise FileExistsError(f'{out} exists; earlier handoffs are never overwritten')
        out.mkdir()
        files = {}
        for key, name in (('output', 'final.mp4'), ('captions', 'captions.srt')):
            if v.get(key):
                shutil.copy2(v[key], out / name)
                files[name] = str(out / name)
        if v.get('recipe'):
            # The renderer's recipe has start_at but not the end of the chosen section; add it so a replay is bounded.
            recipe = json.loads(Path(v['recipe']).read_text())
            window = v.get('window') or {'start': float(recipe.get('start_at') or 0), 'end': None}
            recipe['window'] = window
            recipe['max_seconds'] = None if window.get('end') is None else round(window['end'] - window['start'], 3)
            recipe['source'] = project['source']
            (out / 'recipe.json').write_text(json.dumps(recipe, indent=1))
            files['recipe.json'] = str(out / 'recipe.json')
        p = probe(out / 'final.mp4')
        checks = {'portrait_9_16': bool(p['width'] and p['height'] and abs(p['width'] / p['height'] - 9 / 16) < 0.01),
                  'has_audio': p['audio'], 'sha256_matches_version': sha256(out / 'final.mp4') == v['sha256'],
                  'source_matches_intake': sha256(project['source']) == project['source_sha256']}
        handoff = {'project_id': project_id, 'version': v['version'], 'source': project['source'],
                   'source_original': project.get('source_original'), 'source_sha256': project['source_sha256'],
                   'window': v.get('window'), 'files': files, 'sha256': v['sha256'], 'probe': p, 'checks': checks,
                   'history': [{k: x.get(k) for k in ('version', 'kind', 'note', 'changed', 'could_not_change')}
                               for x in project['versions']],
                   'not_done': 'Not published or sent anywhere. Visual quality needs the creator\'s own review.'}
        (out / 'handoff.json').write_text(json.dumps(handoff, indent=1))
    return {'ok': all(checks.values()), 'folder': str(out), **handoff}


# ---------- MCP wiring ----------

def build_server():
    from mcp.server.fastmcp import FastMCP
    from typing import Optional, List
    from pydantic import BaseModel, Field

    class Edit(BaseModel):
        model_config = {'extra': 'forbid'}
        style: Optional[str] = Field(None, description='Treatment letter (A/B/C) or style name')
        captions_from: Optional[str] = Field(None, description='Take the caption look from this letter or style')
        trim_start: Optional[float] = Field(None, ge=0, le=30, description='Seconds to cut from the opening')
        punchier: Optional[bool] = Field(None, description='Shorter, faster title intro')
        title: Optional[str] = Field(None, description='New title text')
        quieter_music: Optional[bool] = Field(None, description='Music bed 6 dB quieter, if the version has one')

    mcp = FastMCP('video-studio', log_level='WARNING', instructions='Send footage, describe the result, direct the next version in conversation. '
                  'Every tool takes check_only=true for a read-only readiness check that renders nothing. Local only: no uploads, no paid calls, no publishing. Every revision is a new version; old ones are kept.')

    def wrap(fn, *a, **k):
        try:
            return fn(*a, **k)
        except Exception as exc:  # report, never fake success
            return {'ok': False, 'error': f'{type(exc).__name__}: {exc}'}

    @mcp.tool(name='propose_treatments', description='Start a project from a local video file and render its opening in 2-3 visibly different styles '
              '(default A clean short, B brain rot, C dither; also mono-kinetic). Returns a question and one preview per option. '
              'Captions need words: pass `script` (the spoken words), or `model` (a local whisper.cpp model path; or set STUDIO_WHISPER_MODEL) to transcribe once at intake. Local only, no spend.')
    def _propose(source: str, title: str = '', script: str = '', seconds: float = 6.0, styles: Optional[List[str]] = None, model: Optional[str] = None, check_only: bool = False) -> dict:
        return readiness('propose_treatments') if check_only else wrap(propose_treatments, source, title, script, seconds, styles, model)

    @mcp.tool(name='render_preview', description='Render the treatment the creator picked (letter or style name) as a new version of the project.')
    def _preview(project_id: str, option: str, seconds: Optional[float] = None, check_only: bool = False) -> dict:
        return readiness('render_preview') if check_only else wrap(render_preview, project_id, option, seconds)

    @mcp.tool(name='revise', description='Apply one conversational revision as a new version; the previous version is kept. '
              'Map the creator\'s note onto `edit` and pass their words as `request`. Returns understood, changed and could_not_change.')
    def _revise(project_id: str, edit: Edit, request: str = '', check_only: bool = False) -> dict:
        return readiness('revise') if check_only else wrap(revise, project_id, edit.model_dump(exclude_none=True), request)

    @mcp.tool(name='finish', description='Hand off a version (default the latest): final.mp4, captions.srt, recipe.json and handoff.json in a new folder. '
              'Never uploads, posts or publishes.')
    def _finish(project_id: str, version: Optional[int] = None, check_only: bool = False) -> dict:
        return readiness('finish') if check_only else wrap(finish, project_id, version)

    return mcp


if __name__ == '__main__':
    build_server().run()
