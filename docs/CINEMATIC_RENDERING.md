# Cinematic rendering (free, procedural)

The section renderer is adapted from **Cinematic Skill** by Moh4696:
https://github.com/Moh4696/cinematic-skill

The upstream engine is vendored at `vendor_cinematic_engine.py` under its MIT licence.
See `vendor/CINEMATIC_SKILL_LICENSE` for the required copyright and permission notice.
Upstream source revision: `bf435561c6203f90f971300efe952b68b5ec3417`.

## What this adds

- A continuous camera move through a designed visual board for each narration section.
- Uploaded photos are treated as pinned prints; beats without a photo use animated typographic cards.
- Each visual beat appears using the actual per-paragraph duration returned by the final Phonon voice pass.
- FFmpeg exports H.264/AAC MP4 at 1280x720 and 24 fps.

## Important distinction

This is **not** text-to-video diffusion and does not fabricate photorealistic moving footage.
It is a local procedural renderer: Skia draws the board, cards, camera movement, image treatments and film finish; FFmpeg encodes the frames and voiceover. It has no per-generation API charge and requires no `FAL_KEY`.
Users can upload their own images per beat or let the code-rendered motion graphics carry the scene.

## Runtime dependencies

`skia-python`, `numpy`, `Pillow` and the system `ffmpeg` binary. No new environment variables or database migration are required.
