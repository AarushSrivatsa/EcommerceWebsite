# Cinematic Skill rendering

The application vendors the upstream Cinematic Skill from https://github.com/Moh4696/cinematic-skill under its MIT licence. The upstream engine, asset tools, map builder, sound tools, captions, references and examples live in `vendor/cinematic_skill/`.

## One choice per project

Choose one mode when creating a project:

- **Cinematic Skill** (default): the AI makes one visual beat per narration paragraph. The app automatically searches Wikimedia Commons for relevant photos, checks the reuse licence, and downloads one suitable image per beat where available. No image upload or fallback image is needed.
- **Image**: upload one still image for each section. That image stays on screen while the narration plays.

The choice applies to every section. It can be changed later in Video settings; changing it marks the scenes out of date.

## One-click video generation

Press **Generate video** once. The app renders every section that needs updating, then joins the section MP4s into one final film.

For Cinematic Skill, the app runs the upstream preparation, map, Skia engine, sound-effects, audio-mix, credit and subtitle tools. Every sourced image is limited to Public Domain, CC0, CC BY or CC BY-SA, and its credit/licence is retained. If Commons has no suitable photo for a beat, the upstream visual language (documents, maps, diagrams or typography) is used; this is not a user-provided fallback image.

The app creates a structured beat plan and a repeatable scene using the upstream engine. It does not execute arbitrary LLM-generated Python. The separate upstream `motion-assets` skill is not included, so this is not photorealistic AI video generation.

## Runtime

The upstream renderer exports 1280×720 at 30 fps. It runs with one render worker to reduce memory use on small hosting instances. This does not guarantee that long renders will fit within a 512 MB instance; validate peak memory and execution limits on the deployed service.
