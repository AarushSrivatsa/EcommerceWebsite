# Video rendering workflows

## Current application workflow

The active FastAPI video-generation routes currently use a still-image renderer:

1. Image-generation and image-reroll paths use `media.cinematic_assets.search_and_download()` to source Commons images. That module imports the upstream `fetch_commons.py` client and licence helpers.
2. `POST /scripts/{script_id}/render_sections` calls `media.video_service.render_all_pending()`.
3. Each section is rendered by `media.video_service.render_section_video()`, which calls `media.voice.build_image_video()` to create a titled still-image video with narration.
4. `POST /convert_into_video/{script_id}` calls `media.video_service.convert_into_video()`, which concatenates the rendered section videos with FFmpeg.

In this active workflow, the only file under the vendored Cinematic Skill scripts directory that is imported by the app is `fetch_commons.py`, through `media.cinematic_assets`.

## Separate Cinematic Skill integration

The repository also contains a separate integration implementation in:

- `media/cinematic_renderer.py`
- `media/cinematic_skill_runtime.py`

That implementation can prepare a beat-based Cinematic Skill project and invoke the vendored Skia renderer, asset preparation, map, sound-effects, soundtrack, image-credit and caption scripts. However, the current API route flow has no call site for `render_cinematic_video()`; it is not the renderer currently used by the active section-generation endpoints.

The following vendored scripts are retained because they are dependencies of that separate integration:

- `engine.py` and `render.py` — Skia scene engine and video rendering.
- `get_fonts.py` and `prep_assets.py` — font and image/texture preparation.
- `make_map.py` — map generation when a scene contains locations.
- `build_sfx.py` and `mix_soundtrack.py` — sound-effect synthesis and audio mixing.
- `fetch_commons.py` — image metadata/licensing and credits; also used by the active Commons image-source module.
- `burn_captions.py` and `captions.py` — caption/SRT generation.

The standalone skill installer, agent/plugin manifests, authoring helpers and shipped demo projects are omitted because neither the active API workflow nor the retained integration invokes them.

## Deployment notes

The active section-rendering path and the separate Cinematic Skill integration both use FFmpeg. The latter also uses Skia via `skia-python`, NumPy and Pillow. The Docker image installs the application-level pinned dependencies from the root `requirements.txt`.

Before exposing the API to multiple users or the public internet, add Supabase Auth JWT verification and per-user ownership checks for projects, sections and YouTube channel operations. CORS is not authentication, and the current data model does not associate projects with authenticated users.
