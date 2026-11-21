"""Isolated entrypoint for the complete vendored Cinematic Skill workflow."""
from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
from pathlib import Path

log = logging.getLogger("cinematic_skill")


def render_cinematic_video(
    *,
    story_text: str,
    audio_path: Path,
    output_path: Path,
    duration_sec: float,
    paragraph_durations: list[float] | None,
    visual_plan: list[dict] | None,
    image_paths: list[Path | None],
    project_title: str,
    section_position: int,
    video_type: str | None = None,
) -> Path:
    """Run the full upstream skill in a short-lived worker; keep Skia out of the API."""
    output_path = Path(output_path).resolve()
    audio_path = Path(audio_path).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    config_path = output_path.parent / f"cinematic-render-{section_position}.json"
    config = {
        "story_text": story_text,
        "audio_path": str(audio_path),
        "output_path": str(output_path),
        "duration_sec": float(duration_sec),
        "paragraph_durations": paragraph_durations,
        "visual_plan": visual_plan,
        "image_paths": [str(Path(path).resolve()) if path is not None else None for path in image_paths],
        "project_title": project_title,
        "section_position": int(section_position),
        "video_type": video_type,
    }
    config_path.write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")
    project_root = Path(__file__).resolve().parents[1]
    try:
        result = subprocess.run(
            [sys.executable, "-m", "media.cinematic_renderer", "--config", str(config_path)],
            cwd=project_root,
            capture_output=True,
            text=True,
            check=False,
        )
    finally:
        config_path.unlink(missing_ok=True)

    if result.stdout:
        log.info("Cinematic Skill output: %s", result.stdout.strip()[-4000:])
    if result.returncode:
        details = (result.stderr or result.stdout or "worker exited without diagnostics").strip()
        raise RuntimeError(f"Cinematic Skill workflow failed: {details[-4000:]}")
    if not output_path.is_file() or output_path.stat().st_size < 1024:
        details = (result.stderr or result.stdout or "no output MP4 was created").strip()
        raise RuntimeError(f"Cinematic Skill did not produce a valid MP4: {details[-1600:]}")
    return output_path


def _worker_main(config_path: Path) -> None:
    """Execute the upstream skill's asset, map, sound, render and caption pipeline."""
    config = json.loads(config_path.read_text(encoding="utf-8"))
    config["audio_path"] = Path(config["audio_path"])
    config["output_path"] = Path(config["output_path"])
    config["image_paths"] = [
        Path(path) if path else None for path in config.get("image_paths", [])
    ]
    from media.cinematic_skill_runtime import render_full_skill_video

    render_full_skill_video(**config)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    args = parser.parse_args()
    _worker_main(Path(args.config))
