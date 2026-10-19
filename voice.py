import re
import subprocess
import wave
from pathlib import Path

import numpy as np
from kokoro import KPipeline


DEFAULT_VOICE = 'af_heart'
DEFAULT_WPM = 140
SAMPLE_RATE = 24000
SENTENCE_SILENCE = 0.35
PARAGRAPH_SILENCE = 0.9
MIN_SPEED = 0.5
MAX_SPEED = 2.0

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

_PIPELINE_CACHE = {}
_RATE_CACHE = {}


def _load_pipeline(voice_model):
    lang_code = voice_model[0]

    if lang_code not in _PIPELINE_CACHE:
        _PIPELINE_CACHE[lang_code] = KPipeline(
            lang_code=lang_code,
            device='cpu',
            repo_id='hexgrad/Kokoro-82M',
        )

    return _PIPELINE_CACHE[lang_code]


def _get_audio(result):
    audio = result.audio if hasattr(result, 'audio') else result[2]

    if hasattr(audio, 'detach'):
        audio = audio.detach().cpu().numpy()

    return np.asarray(audio)


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


def _get_speaking_rate(pipeline, voice_model):
    if voice_model not in _RATE_CACHE:
        sample_count = sum(
            len(_get_audio(result))
            for result in pipeline(
                _CALIBRATION_TEXT,
                voice=voice_model,
                speed=1.0,
            )
        )

        duration = sample_count / SAMPLE_RATE
        _RATE_CACHE[voice_model] = (
            _count_words(_CALIBRATION_TEXT) / duration
        )

    return _RATE_CACHE[voice_model]


def _silence(seconds):
    return bytes(int(SAMPLE_RATE * seconds) * 2)


def _write_audio(
    pipeline,
    voice_model,
    paragraphs,
    output_path,
    speed,
    sentence_silence,
    paragraph_silence,
):
    duration_samples = 0

    with wave.open(str(output_path), 'wb') as audio_file:
        audio_file.setframerate(SAMPLE_RATE)
        audio_file.setsampwidth(2)
        audio_file.setnchannels(1)

        for paragraph_index, paragraph in enumerate(paragraphs):
            sentences = _split_sentences(paragraph)

            results = pipeline(
                '\n'.join(sentences),
                voice=voice_model,
                speed=speed,
                split_pattern=r'\n+',
            )

            for sentence_index, result in enumerate(results):
                audio = np.clip(_get_audio(result), -1.0, 1.0)
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

    return duration_samples / SAMPLE_RATE


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


def generate_voiceover(
    story_text,
    output_path,
    target_wpm=DEFAULT_WPM,
    voice_model=DEFAULT_VOICE,
    sentence_silence=SENTENCE_SILENCE,
    paragraph_silence=PARAGRAPH_SILENCE,
):
    paragraphs = _split_paragraphs(story_text)

    if not paragraphs:
        raise ValueError('story_text cannot be empty')

    if target_wpm <= 0:
        raise ValueError('target_wpm must be greater than zero')

    output_path = Path(output_path)

    if output_path.suffix.lower() not in {'.mp3', '.wav'}:
        raise ValueError('output_path must end with .mp3 or .wav')

    output_path.parent.mkdir(parents=True, exist_ok=True)

    wav_path = output_path.with_name(
        f'{output_path.stem}.tmp.wav'
    )

    pipeline = _load_pipeline(voice_model)

    word_count = _count_words(story_text)
    words_per_second = _get_speaking_rate(
        pipeline,
        voice_model,
    )

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

    duration = _write_audio(
        pipeline,
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

        duration = _write_audio(
            pipeline,
            voice_model,
            paragraphs,
            wav_path,
            speed,
            sentence_silence,
            paragraph_silence,
        )

        actual_wpm = word_count / (duration / 60)
        correction_passes = 1

    _save_audio(wav_path, output_path)

    return {
        'audio_path': str(output_path),
        'duration_sec': round(duration, 2),
        'word_count': word_count,
        'target_wpm': target_wpm,
        'actual_wpm': round(actual_wpm, 1),
        'speed_used': round(speed, 4),
        'voice_model': voice_model,
        'correction_passes_used': correction_passes,
    }