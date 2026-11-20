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


## Per-section output modes

Every section can use one of two render modes:

- **Single image** creates a 1920×1080, 30 fps still-image scene with the section narration. It uses the section image, or the first uploaded storyboard image as a fallback.
- **Cinematic Skill** creates the existing 1280×720, 24 fps animated photo-board / typography scene. It can use individual beat photos, a shared section image, or procedural cards when no photo is provided.

The selected mode is stored on the section record. Existing sections default to Cinematic Skill, so existing projects keep their previous behavior. Changing modes marks that section and the assembled film as needing a rebuild; it does not delete uploaded images.

## Small-instance safeguards

- Heavy model work is serialized through the shared memory lock.
- FastEmbed uses one ONNX thread and bounded embedding batches.
- Supabase media downloads stream to disk rather than buffering entire MP4 files in the API process.
- User images are validated as actual image files and limited to 16 megapixels before upload.
- The health endpoint and memory log lines report process RSS plus cgroup container usage/limit/peak where the host exposes those metrics.

These measures reduce avoidable memory spikes; they are not a guarantee that every workload fits in 512 MB. Confirm peaks in Render's Metrics view using representative projects.


## CORS and API exposure

The API allows the local Vite development origin by default. The production frontend is served by the same FastAPI origin, so it does not need cross-origin access. When hosting the frontend separately, set `CORS_ORIGINS` to a comma-separated list of exact trusted origins.

CORS is not authentication. Before exposing this API to multiple users or the public internet, add Supabase Auth JWT verification and per-user ownership checks for projects, sections, and YouTube channel operations. The current data model does not yet associate projects with authenticated users.
