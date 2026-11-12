# What goes into the bot before Share as Template

The xAI template guide (https://x.ai/bot/guides/templates-for-grok-bot, checked 12 Nov 2026) says a template is made from a configured bot and carries its instructions, selected memories, skills, routines and plugins. It gives no file format, no field names, no size limits, no skill frontmatter and no routine schedule keys. The web bot panels (Details, Library) show no Skills or Routines editor, so this is done in the Grok Bot app.

So these files are paste-in source text, one per part the guide names.

| Guide part | File | Format |
|---|---|---|
| Instructions | `instructions.md` | plain text; assumed to paste as the bot's instructions |
| Memories | `memories.md` | one line per memory; assumed |
| Skills | `skills/video-studio/SKILL.md` | the `name`/`description` frontmatter is assumed (Hermes and Claude skill convention), not from the guide |
| Routines | `routines/check-connector.md` | plain text; no schedule set, because the guide has no schedule keys |
| Plugins | `plugins.md` | the Video Studio connector does not travel with a template; see `../MCP/SETUP.md` |
