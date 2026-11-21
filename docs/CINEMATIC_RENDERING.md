# Cinematic Skill rendering

The application now vendors the upstream **Cinematic Skill** project by Moh4696 under its MIT licence. The complete upstream skill instructions, engine, asset tools, map builder, sound tools, caption tools, references and example projects are kept in `vendor/cinematic_skill/`.

Upstream project: https://github.com/Moh4696/cinematic-skill  
Upstream revision: `bf435561c6203f90f971300efe952b68b5ec3417`  
Licence: `vendor/cinematic_skill/LICENSE`

## What happens when a Cinematic Skill section is rendered

1. **Storyboard planning** — the section planner gives every narration paragraph a distinct visual hero, a Wikimedia Commons query, a visual type, camera direction and any explicit geographic places.
2. **Automatic archive discovery** — the app calls the upstream Wikimedia Commons search/metadata client. It selects suitable images only when the licence is Public Domain, CC0, CC BY or CC BY-SA. Non-free and unclear licences are not silently accepted.
3. **Attribution and caching** — the image is copied to Supabase Storage and its title, creator, source page, licence and licence URL are saved on the visual beat. Rebuilds reuse the selected image; they do not repeatedly search for the same image.
4. **Asset preparation** — upstream `prep_assets.py` grades and prepares the photos and generates the board textures. Explicitly named map places can be geocoded with OpenStreetMap Nominatim, then `make_map.py` creates a projected world map using world-atlas.
5. **Scene composition** — the generated project contains the upstream `script.json`, `photos.json`, `audio/timing.json` and an app-composed `scene.py`. It uses the real upstream engine classes: `Film`, `Print`, `Card`, `PaperDoc`, `BigText`, `Counter`, `Stamp`, `PenMark`, `StringLine`, `FilmFrame`, `GeoMap`, `MapPin` and `Route`.
6. **Cinematic render** — the upstream Skia renderer creates a continuous camera move, archive board, timed beats, maps and film finish. FFmpeg encodes at 1280×720, 30 fps, CRF 18.
7. **Sound and finishing** — upstream `build_sfx.py` synthesises effects from the scene cues; `mix_soundtrack.py` mixes them with the Phonon narration; `burn_captions.py --srt-only` creates SRT subtitles; `fetch_commons.py credits` writes image credits.
8. **Delivery** — MP4, narration audio, image-credit Markdown and SRT subtitles are uploaded to Supabase Storage. The section interface shows the source/licence for every Commons image and links to the credits and captions.

## Image-source policy

- Automatic sourcing currently uses Wikimedia Commons, not generic Google Images.
- The app only accepts Public Domain, CC0, CC BY and CC BY-SA material. CC BY / CC BY-SA attribution is retained with the scene.
- Uploaded photos are optional overrides. If Commons has no suitable result, the scene uses the section fallback image when one exists, otherwise the Cinematic Skill's designed document/card/typography treatment.
- Recreated documents are visibly stamped **RECREATION**; they are not presented as authentic archive documents.
- This workflow does not generate photorealistic AI images or AI video. The upstream skill's separate `motion-assets` workflow is not included because it is a separate tool and may require a paid generation provider.

## Other mode

The per-section **Single image** mode remains available and is unchanged: it creates a 1920×1080, 30 fps still-image scene with the narration. Cinematic Skill is the default for existing sections.

## Small Render instance notes

- The full renderer runs with one worker in-process to avoid an additional multiprocessing Python renderer.
- ONNX, BLAS and FFmpeg thread counts are bounded.
- Large Supabase assets stream to disk rather than being buffered in API memory.
- The 1280×720 canvas is retained at 30 fps; only the worker count is reduced.
- The 512 MB target is not a guarantee. Confirm cgroup peak memory and Render service metrics during real renders; rendering long sections may still exceed the free instance's memory or execution limits.

## Upstream workflow scope

Cinematic Skill is an agent skill, not a standalone text-to-video API. The application supplies the narration, timing and LLM-generated beat plan, then runs the upstream asset and rendering tools automatically. The upstream research, story-writing and approval guidance is preserved in `SKILL.md` and its references; the app's existing research and script-generation graph remains responsible for factual research and narration.

## CORS and API exposure

The API allows the local Vite development origin by default. The production frontend is served by the same FastAPI origin, so it does not need cross-origin access. When hosting the frontend separately, set `CORS_ORIGINS` to a comma-separated list of exact trusted origins.

CORS is not authentication. Before exposing this API to multiple users or the public internet, add Supabase Auth JWT verification and per-user ownership checks for projects, sections, and YouTube channel operations. The current data model does not yet associate projects with authenticated users.
