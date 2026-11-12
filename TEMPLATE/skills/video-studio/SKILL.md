---
name: video-studio
description: Turn a creator's footage into a finished vertical short and direct it in conversation through the Video Studio connector. Propose two or three treatments, render the one they pick, apply each note as a new version that says what was understood, what changed and what could not change, and hand off the files. Use whenever the creator sends a clip or asks to edit, cut, caption, restyle, tighten or finish a video. Never publishes or spends.
---

# Video Studio

Send footage. Describe the result. Direct the next version in conversation. Keep control of the project.

## Tools (Video Studio connector)
| Tool | Use it to |
|---|---|
| `propose_treatments` | Start a project from a local clip and render its opening in 2-3 styles (A clean short, B brain rot, C Hermes dither). |
| `render_preview` | Render the treatment the creator picked, as a new version. |
| `revise` | Apply one note as a new version. Returns `understood`, `changed`, `could_not_change`. |
| `finish` | Hand off a version: `final.mp4`, `captions.srt`, `recipe.json`, `handoff.json`. |

No other tools exist. Do not invent tool names.

## The loop
1. **Take the footage.** You need a local file path the connector can read. If you only have a link or an attachment the connector cannot reach, say so and ask for a local path.
2. **Propose.** Call `propose_treatments`. Captions need words. If the connector has a local speech model (`model`, or STUDIO_WHISPER_MODEL on the connector), it transcribes once here. If not, ask for the words that are spoken and pass them as `script`. If the tool says it has no words, ask for the script; do not guess. Show each preview with its letter, plus the `editor_note` pick and why. Ask: "Which one, A, B or C?"
3. **Preview.** Call `render_preview` with their letter. Show the preview and ask what should change.
4. **Revise.** Map their note onto `edit` and pass their own words as `request`:
   | They say | `edit` |
   |---|---|
   | "use the clean look" / "go with A" | `style: "A"` |
   | "captions like B" | `captions_from: "B"` |
   | "cut the first two seconds", "tighter intro" | `trim_start: 2` |
   | "punchier" | `punchier: true` |
   | "call it ..." | `title: "..."` |
   | "lower the music" | `quieter_music: true` |
   Several changes go in one `edit`. Then report in this order:
   - **Understood:** the `understood` list.
   - **Changed:** the `changed` list, with the new preview.
   - **Could not change:** the `could_not_change` list, said plainly. Never hide it.
   - The previous version is kept; say its version number.
5. **Finish.** When they are happy, call `finish` and give them the folder. Tell them: nothing was posted, and the visual check is theirs.

## Rules
- One note in, one new version out. Never overwrite a version.
- If the note asks for something outside the `edit` fields (colour grade, new B-roll, generated shots, transitions), do not fake it. It goes under "could not change".
- If a tool returns `ok: false`, show the error and stop. Do not retry with a guess.
- Do not add captions, cuts or effects the creator did not ask for.
- Never publish, post, upload, send, or spend. Hand that back to the creator.

## Report format
```
Video Studio · project <id> · version <n>
Understood: <...>
Changed: <...>
Could not change: <... or nothing>
Preview: <path>   Kept: version <n-1>
```
