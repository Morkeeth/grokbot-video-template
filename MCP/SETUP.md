# Video Studio connector: setup

A Grok Bot template carries instructions, memories, skills and routines. It does not carry custom code or a custom MCP server (xAI template guide, https://x.ai/bot/guides/templates-for-grok-bot, checked 12 Nov 2026). So whoever installs the template runs this connector separately.

## Needs
- Python 3.10 or newer, `pip install "mcp>=1.29,<2" pillow` (mcp 2.x removed FastMCP, which the connector uses)
- ffmpeg and ffprobe on PATH
- The Video Studio engine: a clone of `github.com/Morkeeth/hermes-studio`. Tested at commit `dc4a981` (main on 12 Nov 2026; 16 tests and the demo pass). Set `STUDIO_PATH` to it. The older name `HERMES_STUDIO_PATH` still works; `STUDIO_PATH` wins when both are set.
- Optional: macOS `say` or `espeak` for the demo voice.
- Optional: whisper.cpp (`whisper-cli` on PATH) and a local model for real transcripts. Set `STUDIO_WHISPER_MODEL=/path/to/ggml-model.bin`, or pass `model` to `propose_treatments`. The clip is transcribed once at intake; every later version reuses those words. Without a model, pass the spoken words as `script`. The connector never downloads a model.

## Run it locally (stdio)
```sh
export STUDIO_PATH=/path/to/hermes-studio   # the Video Studio engine clone
export STUDIO_WORKDIR=~/GrokbotStudio      # where projects and versions are written
python3 MCP/studio_mcp.py                   # speaks MCP over stdio
```
Check it with `python3 -m unittest discover -s tests` and `python3 demo/run_demo.py /tmp/studio-demo`.

## Connect it to Grok Bot: two routes, neither proven yet
| Route | What it needs | State |
|---|---|---|
| Custom connector: grok.com/connectors > New Connector > Custom > MCP server URL | A public HTTPS MCP URL. This server speaks stdio today; it would need an HTTP transport (`mcp.run(transport="streamable-http")`) behind a tunnel or host, plus auth. | not proven |
| Local Grok Bot app settings: `~/.grokbot/settings.json`, key `mcpBoxServers` | The key exists and is a list (checked 12 Nov, values not read). The entry shape that Grok Bot accepts was never verified. | not proven |

Do not expose this server on a public URL without auth: it reads local files you name and writes renders.

## What it will never do
Upload, publish, post, send, or call a paid model. Every render goes to a new version folder; nothing is overwritten.
