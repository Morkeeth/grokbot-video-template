# Routine: check the Video Studio connector (on demand)

No schedule is set here: the template guide names no schedule fields (assumed: the creator sets one in the app if they want it).

Goal: tell the creator, in one line, whether the connector can render right now, before they send footage.

Steps:
1. Call each of the four tools with `check_only: true`. The other required inputs are placeholders and are not used:
   - `propose_treatments` with `source: "check"`
   - `render_preview` with `project_id: "check"`, `option: "A"`
   - `revise` with `project_id: "check"`, `edit: {}`
   - `finish` with `project_id: "check"`
2. If a tool is missing, a call fails, or any result has `ready: false`, say "Video Studio needs setup", list the `missing` items, and link SETUP.md.
3. Only if all four return `ready: true`, say "Video Studio is ready to render".

A check renders nothing, uploads nothing and spends nothing. It checks Hermes Studio, ffmpeg, ffprobe and the work folder. It does not prove the look of a render.
