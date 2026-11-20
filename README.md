# Grok Bot Video Studio template

Compare caption styles on a clip, pick one, and revise it without losing the previous cut.

You give it a short clip. It shows the opening in two or three caption styles. You pick one and it renders that version. Then you give a note in plain words ("cleaner look, tighter intro, quieter music") and it makes a new version. Each version says what it understood, what it changed and what it could not change. Old versions stay. Nothing is uploaded or posted.

Today this runs on your own machine, as a tool that a coding agent (or you) can call over MCP. It is written as a Grok Bot template, but **the Grok Bot connection is not yet verified**. Nobody has run it end to end inside Grok Bot yet.

## What is in here
| Folder | What |
|---|---|
| `MCP/` | The Video Studio connector: `studio_mcp.py` (four tools), `client.py`, `SETUP.md`. |
| `demo/` | `run_demo.py`: the first five minutes. A generated sample clip, three styles, a pick, one revision, an MP4. |
| `tests/` | Connector tests: schemas, error paths, one full round trip through an MCP client, and regression tests for bugs found in review. |
| `TEMPLATE/` | Paste-in text for each part of a Grok Bot template: instructions, memories, skills, routines, plugins. The file formats are a guess; see `TEMPLATE/README.md`. |

## Tools
| Tool | Does |
|---|---|
| `propose_treatments` | Shows the opening of the clip in 2 or 3 styles. Returns a question and previews. |
| `render_preview` | Renders the picked style as version 1. |
| `revise` | Turns one note into a new version. Returns `understood`, `changed`, `could_not_change`. |
| `finish` | Copies a version to a handoff folder with captions, recipe and checks. Never publishes. |

## What works and what does not (20 Nov 2026)
| Item | State | How to check |
|---|---|---|
| Four tools, their schemas, and one full round trip through an MCP client | works | `python3 -m unittest discover -s tests` |
| Caption style and chosen section kept across revisions; source clip frozen at intake; one lock per project | works | `tests/test_review_fixes.py`, `tests/test_rereview_fixes.py` |
| Demo makes an MP4 (1080x1920, 30 fps, h264 and aac, 11.5 s) with no keys, no network and no paid call | works | `python3 demo/run_demo.py /tmp/studio-demo`, then `ffprobe` the `final.mp4` it prints |
| A revision says what it could not change (for example music bed or colour grade) | works | the round trip test checks it |
| Uses the Video Studio engine as is, without changing it | works | imported read-only from [Morkeeth/hermes-studio](https://github.com/Morkeeth/hermes-studio), tested at commit `dc4a981` |
| Real footage with real transcription (whisper.cpp) and a music bed | not tested here | the engine supports it; the demo uses a known script |
| Grok Bot calls these tools | not tested | no connector route has been run; see `MCP/SETUP.md` |
| Grok Bot accepts the `TEMPLATE/` files as pasted | not tested | the xAI guide gives no file format |
| Template listed in Grok Bot | not done | |

## Run

You need Python 3.10 or newer, Git, and ffmpeg with ffprobe on your PATH.
On macOS: `brew install ffmpeg`. On Debian or Ubuntu: `sudo apt-get install ffmpeg`.
These are system tools, not pip packages.

```sh
git clone https://github.com/Morkeeth/grokbot-video-template.git
cd grokbot-video-template
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt            # mcp below 2, pillow
git clone https://github.com/Morkeeth/hermes-studio   # the Video Studio engine; tested at commit dc4a981
export STUDIO_PATH=$PWD/hermes-studio
python3 -m unittest discover -s tests
python3 demo/run_demo.py /tmp/studio-demo
```

The tests take about two minutes and print nothing until they finish. A good run ends with `OK` and no `skipped`. If you see `OK (skipped=13)`, `STUDIO_PATH` is not set, so the engine tests did not run.

The demo prints a JSON report. The last step names the finished `final.mp4`. Open it to check that it plays.

No uploads, no paid calls, no publishing. Every render goes to a new folder.

## License

MIT. See `LICENSE`.
