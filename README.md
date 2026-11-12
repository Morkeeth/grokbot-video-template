# Grok Bot Video Studio template

Send footage. Describe the result. Direct the next version in conversation. Keep control of the project.

A creator sends a clip to Grok Bot. The bot shows two or three looks, renders the one they pick, and turns each note ("cleaner look, tighter intro, quieter music") into a new version. Each version says what was understood, what changed and what could not change. Old versions stay. Nothing is posted for them.

## What is in here
| Folder | What |
|---|---|
| `TEMPLATE/` | Paste-in text for each part the xAI guide names: instructions, memories, skills, routines, plugins. File formats are assumed; see `TEMPLATE/README.md`. |
| `MCP/` | The Video Studio connector: `studio_mcp.py` (four tools over the Video Studio engine), `client.py`, `SETUP.md`. |
| `demo/` | `run_demo.py`: the first five minutes. Generated sample, three looks, a pick, one revision, an MP4. |
| `tests/` | MCP tests: schemas, rejection paths, one full round trip through a stdio client, and one regression test per review finding. |

## Tools
| Tool | Does |
|---|---|
| `propose_treatments` | Opening of the clip in 2-3 styles; returns a question and previews. |
| `render_preview` | The picked style as version 1. |
| `revise` | One note as a new version; returns `understood`, `changed`, `could_not_change`. |
| `finish` | Copies the version to a handoff folder with captions, recipe and checks. Never publishes. |

## State (12 Nov 2026)
| Item | State | Evidence |
|---|---|---|
| Four MCP tools, schemas and one round trip through a stdio MCP client | verified | `python3 -m unittest discover -s tests` |
| Codex review findings fixed (caption look and selected section kept across revisions, frozen source, per-project lock, readiness on every tool) | verified, local only | `tests/test_review_fixes.py`: 6 tests pass now; 5 of them were run on the pre-fix server and failed |
| First-five-minutes demo produces an MP4 (1080x1920, 30 fps, h264 + aac, 11.5 s) with no keys, no network, no paid call | verified, local only | `demo/run_demo.py`; ffprobe; `motion_qa.py` PASS |
| Demo MP4 certified by fleet-ops `render_gate` | not proven | The gate needs owner-approved story and look cards, so the test-pattern MP4 counts only as a local test artifact. Real footage still goes through the gate. |
| Revision reports what it could not change (no music bed, colour grade) | verified, local only | round-trip test asserts it |
| Video Studio engine reused, not rebuilt | verified | Imported read-only from [Morkeeth/hermes-studio](https://github.com/Morkeeth/hermes-studio); tests and demo pass at commit `dc4a981` (main, 12 Nov 2026) |
| Grok Bot calls these tools | not proven | No connector route tested; see `MCP/SETUP.md` |
| TEMPLATE parts match the guide (instructions, memories, skills, routines, plugins) | verified against the guide | xAI template guide, read 12 Nov 00:55 |
| SKILL.md frontmatter, memory line format, routine text format | assumed | The guide defines no schema, size limits or schedule keys |
| The Grok Bot app accepts these as pasted | not proven | Web panels show no Skills or Routines editor; packaging is in the app |
| Template published | not done | Share as Template > Publish is the owner's click |
| Handed-off `recipe.json` keeps the chosen section (`window`, `max_seconds`) | verified, local only | `tests/test_rereview_fixes.py` |
| Speech model route: `model` or STUDIO_WHISPER_MODEL, transcribed once at intake; clear error when there are no words | verified with a mocked transcriber | `tests/test_rereview_fixes.py`; a real whisper.cpp run was not done here |
| Real footage, real transcription (whisper.cpp), music bed | not proven | Supported by the Video Studio engine; demo uses a known script |

## Run
```sh
pip install -r requirements.txt            # mcp below 2, pillow; ffmpeg on PATH
git clone https://github.com/Morkeeth/hermes-studio   # the Video Studio engine; tested at commit dc4a981, see MCP/SETUP.md
export STUDIO_PATH=$PWD/hermes-studio
python3 -m unittest discover -s tests
python3 demo/run_demo.py /tmp/studio-demo
```

No uploads, no paid calls, no publishing. Every render is a new folder.
