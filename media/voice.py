"""Phonon voice generation and still-image video rendering helpers."""
from __future__ import annotations

import os
import re
import subprocess
import wave
from pathlib import Path


import memory


# Phonon configuration. The model and voice can be overridden through environment variables.
MODEL_PATH = os.getenv("PHONON_MODEL_PATH", "hf://gradium/phonon-31m-en")
MODEL_QUANT = os.getenv("PHONON_QUANT", "q8")
DEFAULT_VOICE = os.getenv("PHONON_VOICE", "Zoey")
DEFAULT_WPM = 140
SAMPLE_RATE = 24000

SENTENCE_SILENCE = 0.35
PARAGRAPH_SILENCE = 0.9
MIN_DURATION_DELTA = -0.3  # negative = faster in Phonon
MAX_DURATION_DELTA = 0.3   # positive = slower in Phonon
DURATION_DELTA_GAIN = 0.3

# Keep each synthesis request comfortably short. Phonon handles longer text too, but short
# sentence-sized requests are easier to recover from and keep peak working memory bounded.
WINDOW_CHARS = 180
WINDOW_SILENCE = 0.08

VIDEO_SIZE = (1920, 1080)
VIDEO_FPS = 30
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}

_CALIBRATION_TEXT = (
    "The old lighthouse stood quietly at the edge of the cliff, its light sweeping "
    "slowly across the dark water below. Waves rolled in without hurry, one after "
    "another, folding softly onto the sand. Somewhere in the distance a bell buoy "
    "rang, a low and steady sound that seemed to belong to the night itself. Nothing "
    "moved quickly here. Even the wind took its time, drifting through the tall "
    "grass on the dunes and settling again. A single boat light blinked far out on "
    "the horizon, patient and unhurried, as if it too understood there was nowhere "
    "else it needed to be."
)

# Older projects still contain Kokoro voice IDs. They are mapped to the new default rather
# than passed to Phonon's catalogue as if they were valid Phonon voices.
_LEGACY_KOKORO_PREFIXES = ("af_", "am_", "bf_", "bm_")
_LEGACY_ZOEY_IDS = {"en_us_zoey", "default"}

_PHONON = None
_RATE_CACHE: dict[str, float] = {}


def _resolve_voice(voice_model: str | None) -> str:
    """Resolve a saved project voice to a Phonon catalogue voice."""
    voice = (voice_model or DEFAULT_VOICE).strip()
    lowered = voice.lower()

    if lowered in _LEGACY_ZOEY_IDS or lowered.startswith(_LEGACY_KOKORO_PREFIXES):
        return DEFAULT_VOICE

    return voice


def _load_phonon():
    """Load one Phonon model instance, reusing it until release_model() is called."""
    global _PHONON

    if _PHONON is None:
        import ptts
        _PHONON = ptts.TTS(
            MODEL_PATH,
            lang="en",
            quant=MODEL_QUANT,
        )

        if _PHONON.sample_rate != SAMPLE_RATE:
            actual_rate = _PHONON.sample_rate
            release_model()
            raise RuntimeError(
                f"Expected Phonon to produce {SAMPLE_RATE} Hz audio, got {actual_rate} Hz"
            )

        memory.report("Phonon model loaded")

    return _PHONON


def release_model():
    """Drop Phonon from memory before the embedding model or ffmpeg needs RAM."""
    global _PHONON
    _PHONON = None
    memory.free()


def _windows(text: str, limit: int = WINDOW_CHARS) -> list[str]:
    """Split long text at punctuation where possible, otherwise between words."""
    pieces = []

    while len(text) > limit:
        window = text[:limit]
        cut = max(window.rfind(mark) for mark in (",", ";", ":"))

        if cut < limit // 3:
            cut = window.rfind(" ")
        if cut <= 0:
            cut = limit - 1

        pieces.append(text[: cut + 1].strip())
        text = text[cut + 1 :].strip()

    if text:
        pieces.append(text)

    return pieces


def _speak_piece(text: str, voice_model: str) -> np.ndarray:
    """Synthesize one short text piece with Phonon."""
    import numpy as np
    audio = _load_phonon().synth(text, voice=voice_model)
    audio = np.asarray(audio, dtype=np.float32)

    if audio.ndim != 1:
        raise RuntimeError(f"Phonon returned an unexpected audio shape: {audio.shape}")
    if audio.size == 0:
        raise RuntimeError("Phonon returned empty audio")

    return audio


def _speak(
    text: str,
    voice_model: str,
    duration_delta: float = 0.0,
) -> np.ndarray:
    """Speak one sentence, splitting unusually long sentences into smaller pieces."""
    import numpy as np
    model = _load_phonon()
    model.set_conditions({"duration_delta": float(duration_delta)})

    pieces = _windows(text)
    if not pieces:
        return np.zeros(0, dtype=np.float32)

    audio_parts = [_speak_piece(piece, voice_model) for piece in pieces]

    if len(audio_parts) == 1:
        return audio_parts[0]

    gap = np.zeros(int(SAMPLE_RATE * WINDOW_SILENCE), dtype=np.float32)
    joined = []
    for index, part in enumerate(audio_parts):
        joined.append(part)
        if index < len(audio_parts) - 1:
            joined.append(gap)

    return np.concatenate(joined)


def _count_words(text: str) -> int:
    return len(text.split())


def _split_paragraphs(text: str) -> list[str]:
    paragraphs = re.split(r"\n\s*\n", text.strip())
    return [
        " ".join(paragraph.split())
        for paragraph in paragraphs
        if paragraph.strip()
    ]


def _split_sentences(text: str) -> list[str]:
    return [
        sentence
        for sentence in re.split(r"(?<=[.!?])\s+", text.strip())
        if sentence
    ]


def _get_speaking_rate(voice_model: str) -> float:
    """Measure this Phonon voice's natural words-per-second at duration_delta=0."""
    if voice_model not in _RATE_CACHE:
        sample_count = sum(
            len(_speak(sentence, voice_model, duration_delta=0.0))
            for sentence in _split_sentences(_CALIBRATION_TEXT)
        )

        duration = sample_count / SAMPLE_RATE
        if duration <= 0:
            raise RuntimeError("Could not measure Phonon's natural speaking rate")

        _RATE_CACHE[voice_model] = _count_words(_CALIBRATION_TEXT) / duration

    return _RATE_CACHE[voice_model]


def _clamp_duration_delta(value: float) -> float:
    return min(max(value, MIN_DURATION_DELTA), MAX_DURATION_DELTA)


def _silence(seconds: float) -> bytes:
    return bytes(int(SAMPLE_RATE * seconds) * 2)  # mono, signed 16-bit PCM


def _write_audio(
    voice_model: str,
    paragraphs: list[str],
    output_path: Path,
    duration_delta: float,
    sentence_silence: float,
    paragraph_silence: float,
) -> tuple[float, list[float]]:
    import numpy as np
    duration_samples = 0
    paragraph_samples = []

    with wave.open(str(output_path), "wb") as audio_file:
        audio_file.setframerate(SAMPLE_RATE)
        audio_file.setsampwidth(2)
        audio_file.setnchannels(1)

        for paragraph_index, paragraph in enumerate(paragraphs):
            paragraph_start = duration_samples
            sentences = _split_sentences(paragraph)

            for sentence_index, sentence in enumerate(sentences):
                audio = np.clip(
                    _speak(sentence, voice_model, duration_delta),
                    -1.0,
                    1.0,
                )
                audio_bytes = (audio * 32767).astype(np.int16).tobytes()
                audio_file.writeframes(audio_bytes)
                duration_samples += len(audio_bytes) // 2

                if sentence_index < len(sentences) - 1:
                    silence = _silence(sentence_silence)
                    audio_file.writeframes(silence)
                    duration_samples += len(silence) // 2

            if paragraph_index < len(paragraphs) - 1:
                silence = _silence(paragraph_silence)
                audio_file.writeframes(silence)
                duration_samples += len(silence) // 2

            paragraph_samples.append(duration_samples - paragraph_start)

    paragraph_durations = [samples / SAMPLE_RATE for samples in paragraph_samples]
    return duration_samples / SAMPLE_RATE, paragraph_durations


def _save_audio(wav_path: Path, output_path: Path) -> None:
    if output_path.suffix.lower() == ".wav":
        wav_path.replace(output_path)
        return

    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-i",
            str(wav_path),
            "-ar",
            "44100",
            "-codec:a",
            "libmp3lame",
            "-b:a",
            "128k",
            str(output_path),
        ],
        check=True,
    )
    wav_path.unlink(missing_ok=True)


def _validate_images(image_paths) -> list[Path]:
    images = [Path(path) for path in image_paths]

    for image in images:
        if not image.is_file():
            raise FileNotFoundError(f"image not found: {image}")

        if image.suffix.lower() not in IMAGE_EXTENSIONS:
            raise ValueError(
                f"unsupported image type: {image.name} "
                f'(use {", ".join(sorted(IMAGE_EXTENSIONS))})'
            )

    return images


def _plan_image_durations(
    paragraph_durations: list[float],
    image_count: int,
    section_paragraph_counts: list[int] | None = None,
) -> list[float]:
    """Allocate the narration timeline across images, keeping changes on paragraph boundaries."""
    if section_paragraph_counts is not None:
        durations = []
        index = 0

        for count in section_paragraph_counts:
            durations.append(sum(paragraph_durations[index : index + count]))
            index += count

        return durations

    total = sum(paragraph_durations)

    if image_count == len(paragraph_durations):
        return list(paragraph_durations)

    durations = [0.0] * image_count
    start = 0.0

    for paragraph_duration in paragraph_durations:
        midpoint = start + paragraph_duration / 2
        index = min(int(midpoint / total * image_count), image_count - 1)
        durations[index] += paragraph_duration
        start += paragraph_duration

    if any(duration <= 0 for duration in durations):
        durations = [total / image_count] * image_count

    return durations


def _concat_line_path(path: Path) -> str:
    escaped = path.resolve().as_posix().replace("'", "'\\''")
    return f"file '{escaped}'"


def _build_video(
    images: list[Path],
    durations: list[float],
    audio_path: Path,
    video_path: Path,
    size: tuple[int, int] = VIDEO_SIZE,
    fps: int = VIDEO_FPS,
) -> None:
    width, height = size
    list_path = video_path.with_name(f"{video_path.stem}.tmp.txt")

    lines = []
    for image, duration in zip(images, durations):
        lines.append(_concat_line_path(image))
        lines.append(f"duration {duration:.4f}")

    # The concat demuxer ignores the final duration unless the last image is repeated.
    lines.append(_concat_line_path(images[-1]))
    list_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    video_filter = (
        f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black,"
        "setsar=1,format=yuv420p"
    )

    try:
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-loglevel",
                "error",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(list_path),
                "-i",
                str(audio_path),
                "-vf",
                video_filter,
                "-filter_threads",
                "1",
                "-r",
                str(fps),
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-tune",
                "stillimage",
                "-x264-params",
                "rc-lookahead=0:sync-lookahead=0:bframes=0",
                "-threads",
                "1",
                "-crf",
                "20",
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                "-movflags",
                "+faststart",
                "-shortest",
                str(video_path),
            ],
            check=True,
        )
    finally:
        list_path.unlink(missing_ok=True)


def build_image_video(
    image_path: Path,
    audio_path: Path,
    video_path: Path,
    duration_sec: float,
) -> None:
    """Create the original single-still scene mode at the same 1080p/30fps quality."""
    duration = max(0.1, float(duration_sec))
    _build_video(
        [Path(image_path)],
        [duration],
        Path(audio_path),
        Path(video_path),
        size=VIDEO_SIZE,
        fps=VIDEO_FPS,
    )


def generate_voiceover(
    story_text,
    output_path,
    target_wpm=DEFAULT_WPM,
    voice_model=DEFAULT_VOICE,
    sentence_silence=SENTENCE_SILENCE,
    paragraph_silence=PARAGRAPH_SILENCE,
    image_paths=None,
    video_path=None,
    section_paragraph_counts=None,
):
    """Generate a Phonon voiceover and, optionally, a still-image video for it."""
    paragraphs = _split_paragraphs(story_text)

    if not paragraphs:
        raise ValueError("story_text cannot be empty")
    if target_wpm <= 0:
        raise ValueError("target_wpm must be greater than zero")

    output_path = Path(output_path)
    if output_path.suffix.lower() not in {".mp3", ".wav"}:
        raise ValueError("output_path must end with .mp3 or .wav")

    voice_model = _resolve_voice(voice_model)
    images = _validate_images(image_paths) if image_paths else []

    if section_paragraph_counts is not None and images and (
        len(section_paragraph_counts) != len(images)
        or sum(section_paragraph_counts) != len(paragraphs)
    ):
        raise ValueError(
            "section_paragraph_counts must have one entry per image "
            "and add up to the number of paragraphs"
        )

    if images:
        video_path = (
            Path(video_path)
            if video_path
            else output_path.with_suffix(".mp4")
        )
        if video_path.suffix.lower() != ".mp4":
            raise ValueError("video_path must end with .mp4")
        video_path.parent.mkdir(parents=True, exist_ok=True)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    wav_path = output_path.with_name(f"{output_path.stem}.tmp.wav")

    word_count = _count_words(story_text)
    sentence_count = sum(
        len(_split_sentences(paragraph))
        for paragraph in paragraphs
    )
    pause_duration = (
        (sentence_count - len(paragraphs)) * sentence_silence
        + (len(paragraphs) - 1) * paragraph_silence
    )

    target_duration = word_count / target_wpm * 60
    desired_speech_duration = max(1.0, target_duration - pause_duration)

    duration_delta = 0.0
    duration = 0.0
    paragraph_durations = []
    correction_passes = 0

    try:
        natural_words_per_second = _get_speaking_rate(voice_model)
        natural_speech_duration = word_count / natural_words_per_second
        speed_factor = natural_speech_duration / desired_speech_duration

        # Phonon uses a duration_delta condition rather than Kokoro's speed multiplier:
        # negative values shorten speech and positive values lengthen it. This first estimate
        # is then corrected once using the actual rendered WPM below.
        duration_delta = _clamp_duration_delta(
            (1.0 - speed_factor) * DURATION_DELTA_GAIN
        )

        duration, paragraph_durations = _write_audio(
            voice_model,
            paragraphs,
            wav_path,
            duration_delta,
            sentence_silence,
            paragraph_silence,
        )

        actual_wpm = word_count / (duration / 60) if duration > 0 else 0.0

        if actual_wpm > 0 and abs(actual_wpm - target_wpm) / target_wpm > 0.02:
            correction = (target_wpm / actual_wpm - 1.0) * DURATION_DELTA_GAIN
            duration_delta = _clamp_duration_delta(duration_delta - correction)

            duration, paragraph_durations = _write_audio(
                voice_model,
                paragraphs,
                wav_path,
                duration_delta,
                sentence_silence,
                paragraph_silence,
            )
            actual_wpm = word_count / (duration / 60) if duration > 0 else 0.0
            correction_passes = 1

    finally:
        # The embedding model uses the same memory budget. Do not leave Phonon resident
        # after this section has finished generating its audio.
        release_model()

    actual_wpm = word_count / (duration / 60)

    # Build the video from the lossless WAV before _save_audio moves or deletes it.
    if images:
        image_durations = _plan_image_durations(
            paragraph_durations,
            len(images),
            section_paragraph_counts,
        )
        try:
            _build_video(images, image_durations, wav_path, video_path)
        except Exception:
            wav_path.unlink(missing_ok=True)
            raise

    _save_audio(wav_path, output_path)

    result = {
        "audio_path": str(output_path),
        "duration_sec": round(duration, 2),
        "word_count": word_count,
        "target_wpm": target_wpm,
        "actual_wpm": round(actual_wpm, 1),
        "speed_used": round(speed_factor, 4),
        "duration_delta_used": round(duration_delta, 4),
        "voice_model": voice_model,
        "correction_passes_used": correction_passes,
        # Exact per-paragraph durations from the final Phonon pass; the cinematic renderer
        # uses these to time image arrivals and camera moves to the actual narration.
        "paragraph_durations_sec": [round(value, 4) for value in paragraph_durations],
    }

    if images:
        result["video_path"] = str(video_path)
        result["image_count"] = len(images)
        result["image_durations_sec"] = [round(value, 2) for value in image_durations]

    return result
