from __future__ import annotations

import struct

import pytest

from backend.models import TtsResult, VisemeEvent
from backend.services.mixed_language_tts import segment_text_by_language, stitch_tts_results


class _Det:
    def __init__(self, language: str):
        self.language = language
        self.score = 1.0


def _fake_detect(text: str):
    t = (text or "").lower()
    # Tiny heuristic for tests only.
    if "how are you" in t or "hello mate" in t or "hello" in t:
        return _Det("en")
    if "jak" in t or "máš" in t or "se" in t:
        return _Det("cs")
    return None


def test_segmentation_examples():
    segs = segment_text_by_language("Jak se máš, hello?", detect_language=_fake_detect)
    assert len(segs) == 1
    assert segs[0].language == "cs"

    segs = segment_text_by_language("Jak se máš, hello mate?", detect_language=_fake_detect)
    assert len(segs) == 1
    assert segs[0].language == "cs"

    segs = segment_text_by_language("Jak se máš, how are you?", detect_language=_fake_detect)
    assert [s.language for s in segs] == ["cs", "en"]

    # Leading short prefix (<3 words) merges into the next detected segment.
    segs = segment_text_by_language("Jak máš, how are you?", detect_language=_fake_detect)
    assert len(segs) == 1
    assert segs[0].language == "en"


def _wav_pcm_16khz_mono(pcm: bytes) -> bytes:
    # Minimal PCM wav header.
    num_channels = 1
    sample_rate = 16000
    bits_per_sample = 16
    block_align = num_channels * (bits_per_sample // 8)
    byte_rate = sample_rate * block_align
    fmt_chunk = struct.pack(
        "<4sIHHIIHH",
        b"fmt ",
        16,
        1,
        num_channels,
        sample_rate,
        byte_rate,
        block_align,
        bits_per_sample,
    )
    data_chunk = struct.pack("<4sI", b"data", len(pcm)) + pcm
    riff_size = 4 + len(fmt_chunk) + len(data_chunk)
    header = struct.pack("<4sI4s", b"RIFF", riff_size, b"WAVE")
    return header + fmt_chunk + data_chunk


def test_stitch_wav_and_visemes_offsets():
    # 16-bit mono: 2 bytes/sample. 16k samples/s => 32k bytes/s => 32 bytes/ms.
    pcm1 = b"\x00\x00" * 160  # 160 samples = 10ms
    pcm2 = b"\x00\x00" * 320  # 320 samples = 20ms

    w1 = _wav_pcm_16khz_mono(pcm1)
    w2 = _wav_pcm_16khz_mono(pcm2)

    r1 = TtsResult(audio_data=w1, visemes=[VisemeEvent(id=1, offset_ms=0.0)], duration_ms=10.0, characters_synthesized=3)
    r2 = TtsResult(audio_data=w2, visemes=[VisemeEvent(id=2, offset_ms=5.0)], duration_ms=20.0, characters_synthesized=4)

    out = stitch_tts_results([r1, r2])
    assert out.audio_data.startswith(b"RIFF")
    assert out.duration_ms == pytest.approx(30.0, abs=0.5)
    assert [v.id for v in out.visemes] == [1, 2]
    # Second segment shifted by first duration (10ms): 5ms -> 15ms
    assert out.visemes[1].offset_ms == pytest.approx(15.0, abs=0.25)
    assert out.characters_synthesized == 7

