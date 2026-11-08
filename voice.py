import os
import re
import subprocess
import wave
from pathlib import Path

import numpy as np
from kokoro_onnx import Kokoro

import memory


DEFAULT_VOICE = 'af_heart'
DEFAULT_WPM = 140
SAMPLE_RATE = 24000          # what Kokoro produces
SENTENCE_SILENCE = 0.35
PARAGRAPH_SILENCE = 0.9
MIN_SPEED = 0.5
MAX_SPEED = 2.0

# Kokoro's working memory grows with the length of the text it speaks at once (about 250 MB for 40 characters,
# 360 MB for 120, 510 MB for 200, 870 MB for 450). So sentences are spoken in pieces of at most this many characters.
WINDOW_CHARS = 70
WINDOW_SILENCE = 0.08
RELOAD_EVERY = 6          # pieces spoken before the voice model is loaded afresh

VIDEO_SIZE = (1920, 1080)
VIDEO_FPS = 30
IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp', '.bmp'}

_CALIBRATION_TEXT = (
    'The old lighthouse stood quietly at the edge of the cliff, its light sweeping '
    'slowly across the dark water below. Waves rolled in without hurry, one after '
    'another, folding softly onto the sand. Somewhere in the distance a bell buoy '
    'rang, a low and steady sound that seemed to belong to the night itself. Nothing '
    'moved quickly here. Even the wind took its time, drifting through the tall '
    'grass on the dunes and settling again. A single boat light blinked far out on '
    'the horizon, patient and unhurried, as if it too understood there was nowhere '
    'else it needed to be.'
)

# Kokoro runs through ONNX Runtime (no PyTorch). Models: kokoro-v1.0.onnx (full quality)
# or kokoro-v1.0.int8.onnx (smaller and lighter), plus voices-v1.0.bin.
MODEL_PATH = os.getenv('KOKORO_MODEL_PATH', 'models/kokoro-v1.0.onnx')
VOICES_PATH = os.getenv('KOKORO_VOICES_PATH', 'models/voices-v1.0.bin')

# first letter of a Kokoro voice name -> the language code kokoro-onnx wants
LANGUAGES = {
    'a': 'en-us', 'b': 'en-gb', 'e': 'es', 'f': 'fr-fr',
    'h': 'hi', 'i': 'it', 'j': 'ja', 'p': 'pt-br', 'z': 'cmn',
}

_KOKORO = None
_USES = 0
_RATE_CACHE = {}


def _load_kokoro():
    global _KOKORO, _USES

    # ONNX Runtime keeps buffers for every text length it has seen, so its RAM creeps up while it speaks.
    # A fresh model every few pieces (loading takes about a second) keeps that bounded.
    if _KOKORO is not None and _USES >= RELOAD_EVERY:
        release_model()

    if _KOKORO is None:
        _KOKORO = Kokoro(MODEL_PATH, VOICES_PATH)
        _USES = 0

    _USES += 1
    return _KOKORO


def release_model():
    """Drops the voice model from memory (it loads again, in about a second, when it is next needed)."""
    global _KOKORO
    _KOKORO = None
    memory.free()


def _windows(text, limit=None):
    """Cuts a long sentence into pieces of at most `limit` characters, at a comma, semicolon or colon when
    there is one, otherwise between words."""
    limit = limit or WINDOW_CHARS
    pieces = []
    while len(text) > limit:
        window = text[:limit]
        cut = max(window.rfind(mark) for mark in (',', ';', ':'))
        if cut < limit // 3:                          # no good punctuation: cut at the last space
            cut = window.rfind(' ')
        if cut <= 0:                                  # one enormous word: cut anywhere
            cut = limit - 1
        pieces.append(text[:cut + 1].strip())
        text = text[cut + 1:].strip()
    if text:
        pieces.append(text)
    return pieces


def _speak(text, voice_model, speed):
    """Speak a sentence and return the audio as a float array (long sentences piece by piece)."""
    pieces = _windows(text)
    if len(pieces) == 1:
        return _speak_piece(pieces[0], voice_model, speed)

    gap = np.zeros(int(SAMPLE_RATE * WINDOW_SILENCE), dtype=np.float32)
    parts = []
    for piece in pieces:
        parts += [_speak_piece(piece, voice_model, speed), gap]
    return np.concatenate(parts[:-1])


def _speak_piece(text, voice_model, speed):
    audio, sample_rate = _load_kokoro().create(
        text,
        voice=voice_model,
        speed=speed,
        lang=LANGUAGES.get(voice_model[0], 'en-us'),
    )

    if sample_rate != SAMPLE_RATE:
        raise RuntimeError(f'expected {SAMPLE_RATE} Hz audio, got {sample_rate}')

    return audio


def _count_words(text):
    return len(text.split())


def _split_paragraphs(text):
    paragraphs = re.split(r'\n\s*\n', text.strip())
    return [
        ' '.join(paragraph.split())
        for paragraph in paragraphs
        if paragraph.strip()
    ]


def _split_sentences(text):
    return [
        sentence
        for sentence in re.split(r'(?<=[.!?])\s+', text.strip())
        if sentence
    ]


def _get_speaking_rate(voice_model):
    if voice_model not in _RATE_CACHE:
        sample_count = sum(
            len(_speak(sentence, voice_model, 1.0))
            for sentence in _split_sentences(_CALIBRATION_TEXT)
        )

        duration = sample_count / SAMPLE_RATE
        _RATE_CACHE[voice_model] = (
            _count_words(_CALIBRATION_TEXT) / duration
        )

    return _RATE_CACHE[voice_model]


def _silence(seconds):
    return bytes(int(SAMPLE_RATE * seconds) * 2)


def _write_audio(
    voice_model,
    paragraphs,
    output_path,
    speed,
    sentence_silence,
    paragraph_silence,
):
    duration_samples = 0
    paragraph_samples = []

    with wave.open(str(output_path), 'wb') as audio_file:
        audio_file.setframerate(SAMPLE_RATE)
        audio_file.setsampwidth(2)
        audio_file.setnchannels(1)

        for paragraph_index, paragraph in enumerate(paragraphs):
            paragraph_start = duration_samples
            sentences = _split_sentences(paragraph)

            for sentence_index, sentence in enumerate(sentences):
                audio = np.clip(_speak(sentence, voice_model, speed), -1.0, 1.0)
                audio_bytes = (
                    audio * 32767
                ).astype(np.int16).tobytes()

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

            # Trailing pause counts toward this paragraph, so the
            # per-paragraph durations add up to the full audio length.
            paragraph_samples.append(duration_samples - paragraph_start)

    paragraph_durations = [
        samples / SAMPLE_RATE for samples in paragraph_samples
    ]

    return duration_samples / SAMPLE_RATE, paragraph_durations


def _save_audio(wav_path, output_path):
    if output_path.suffix.lower() == '.wav':
        wav_path.replace(output_path)
        return

    subprocess.run(
        [
            'ffmpeg',
            '-y',
            '-loglevel',
            'error',
            '-i',
            str(wav_path),
            '-ar',
            '44100',
            '-codec:a',
            'libmp3lame',
            '-b:a',
            '128k',
            str(output_path),
        ],
        check=True,
    )

    wav_path.unlink(missing_ok=True)


def _validate_images(image_paths):
    images = [Path(path) for path in image_paths]

    for image in images:
        if not image.is_file():
            raise FileNotFoundError(f'image not found: {image}')

        if image.suffix.lower() not in IMAGE_EXTENSIONS:
            raise ValueError(
                f'unsupported image type: {image.name} '
                f'(use {", ".join(sorted(IMAGE_EXTENSIONS))})'
            )

    return images


def _plan_image_durations(
    paragraph_durations,
    image_count,
    section_paragraph_counts=None,
):
    """Return how long each image stays on screen.

    With section_paragraph_counts (paragraphs per section, one image per
    section) each image lasts as long as its section's paragraphs.

    Otherwise: one image per paragraph -> each image matches its paragraph.
    Else paragraphs are grouped onto images by timeline position so
    image changes still land on paragraph boundaries. If grouping leaves an
    image with no time (more images than paragraphs), fall back to an even
    split of the whole audio.
    """
    if section_paragraph_counts is not None:
        durations = []
        index = 0

        for count in section_paragraph_counts:
            durations.append(sum(paragraph_durations[index:index + count]))
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

def _concat_line_path(path):
    escaped = path.resolve().as_posix().replace("'", "'\\''")
    return f"file '{escaped}'"


def _build_video(
    images,
    durations,
    audio_path,
    video_path,
    size=VIDEO_SIZE,
    fps=VIDEO_FPS,
):
    width, height = size
    list_path = video_path.with_name(f'{video_path.stem}.tmp.txt')

    lines = []
    for image, duration in zip(images, durations):
        lines.append(_concat_line_path(image))
        lines.append(f'duration {duration:.4f}')

    # concat demuxer ignores the last duration unless the file repeats.
    lines.append(_concat_line_path(images[-1]))
    list_path.write_text('\n'.join(lines) + '\n', encoding='utf-8')

    video_filter = (
        f'scale={width}:{height}:force_original_aspect_ratio=decrease,'
        f'pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black,'
        'setsar=1,format=yuv420p'
    )

    try:
        subprocess.run(
            [
                'ffmpeg',
                '-y',
                '-loglevel',
                'error',
                '-f',
                'concat',
                '-safe',
                '0',
                '-i',
                str(list_path),
                '-i',
                str(audio_path),
                '-vf',
                video_filter,
                '-r',
                str(fps),
                '-c:v',
                'libx264',
                '-preset',
                'veryfast',
                '-tune',
                'stillimage',
                '-x264-params',
                'rc-lookahead=0:sync-lookahead=0:bframes=0',
                '-threads',
                '1',
                '-crf',
                '20',
                '-c:a',
                'aac',
                '-b:a',
                '192k',
                '-movflags',
                '+faststart',
                '-shortest',
                str(video_path),
            ],
            check=True,
        )
    finally:
        list_path.unlink(missing_ok=True)


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
    paragraphs = _split_paragraphs(story_text)

    if not paragraphs:
        raise ValueError('story_text cannot be empty')

    if target_wpm <= 0:
        raise ValueError('target_wpm must be greater than zero')

    output_path = Path(output_path)


    if output_path.suffix.lower() not in {'.mp3', '.wav'}:
        raise ValueError('output_path must end with .mp3 or .wav')

    images = _validate_images(image_paths) if image_paths else []
    if section_paragraph_counts is not None and images and (
        len(section_paragraph_counts) != len(images)
        or sum(section_paragraph_counts) != len(paragraphs)
    ):
        raise ValueError(
            'section_paragraph_counts must have one entry per image '
            'and add up to the number of paragraphs'
        )

    if images:
        video_path = (
            Path(video_path)
            if video_path
            else output_path.with_suffix('.mp4')
        )

        if video_path.suffix.lower() != '.mp4':
            raise ValueError('video_path must end with .mp4')

        video_path.parent.mkdir(parents=True, exist_ok=True)

    output_path.parent.mkdir(parents=True, exist_ok=True)

    wav_path = output_path.with_name(
        f'{output_path.stem}.tmp.wav'
    )

    word_count = _count_words(story_text)
    words_per_second = _get_speaking_rate(voice_model)

    sentence_count = sum(
        len(_split_sentences(paragraph))
        for paragraph in paragraphs
    )

    pause_duration = (
        (sentence_count - len(paragraphs)) * sentence_silence
        + (len(paragraphs) - 1) * paragraph_silence
    )

    target_duration = word_count / target_wpm * 60
    speech_duration = max(
        1,
        target_duration - pause_duration,
    )

    speed = (
        (word_count / words_per_second)
        / speech_duration
    )

    speed = min(
        max(speed, MIN_SPEED),
        MAX_SPEED,
    )

    duration, paragraph_durations = _write_audio(
        voice_model,
        paragraphs,
        wav_path,
        speed,
        sentence_silence,
        paragraph_silence,
    )

    actual_wpm = word_count / (duration / 60)
    correction_passes = 0

    if abs(actual_wpm - target_wpm) / target_wpm > 0.02:
        speed *= duration / target_duration

        speed = min(
            max(speed, MIN_SPEED),
            MAX_SPEED,
        )

        duration, paragraph_durations = _write_audio(
            voice_model,
            paragraphs,
            wav_path,
            speed,
            sentence_silence,
            paragraph_silence,
        )

        actual_wpm = word_count / (duration / 60)
        correction_passes = 1

    release_model()          # the voice is finished: free its memory before ffmpeg needs some

    # Build video from the lossless wav before _save_audio consumes it.
    if images:
        image_durations = _plan_image_durations(
            paragraph_durations,
            len(images),
            section_paragraph_counts,
        )

        try:
            _build_video(
                images,
                image_durations,
                wav_path,
                video_path,
            )
        except Exception:
            wav_path.unlink(missing_ok=True)
            raise

    _save_audio(wav_path, output_path)

    result = {
        'audio_path': str(output_path),
        'duration_sec': round(duration, 2),
        'word_count': word_count,
        'target_wpm': target_wpm,
        'actual_wpm': round(actual_wpm, 1),
        'speed_used': round(speed, 4),
        'voice_model': voice_model,
        'correction_passes_used': correction_passes,
    }

    if images:
        result['video_path'] = str(video_path)
        result['image_count'] = len(images)
        result['image_durations_sec'] = [
            round(value, 2) for value in image_durations
        ]

    return result