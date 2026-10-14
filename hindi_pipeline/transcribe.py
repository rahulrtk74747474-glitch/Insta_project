"""Stage 2: English ASR with word timestamps, readable captions and QA metadata."""
from __future__ import annotations

import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .common import StageProvider, write_srt

END_PUNCT = re.compile(r"[.?!…。？！]+[\"'”’)]*$")
UNSPACED_PUNCT = re.compile(r"\s+([,.:;!?।॥，。！？])")


def _text(words: list[str]) -> str:
    """Whisper word strings may or may not contain leading spaces."""
    value = " ".join(str(w).strip() for w in words if str(w).strip())
    return UNSPACED_PUNCT.sub(r"\1", value).strip()


def _segments_to_cues(segments: Any, max_duration: float, max_chars: int):
    cues, warnings = [], []
    for raw in segments:
        text = str(getattr(raw, "text", "")).strip()
        if not text:
            continue
        start, end = float(raw.start), float(raw.end)
        if not (math.isfinite(start) and math.isfinite(end) and 0 <= start < end):
            warnings.append("Ignored ASR segment with invalid timing")
            continue

        tokens = []
        for word in getattr(raw, "words", None) or []:
            if getattr(word, "start", None) is None or getattr(word, "end", None) is None:
                continue
            a, b = float(word.start), float(word.end)
            if not (math.isfinite(a) and math.isfinite(b) and a >= 0 and b >= 0):
                continue
            token = str(getattr(word, "word", "")).strip()
            if not token:
                continue
            # Some Whisper words have equal start/end timestamps. Preserve their
            # text, but flag the 10ms timing as estimated rather than pretending
            # that the original zero-duration timestamp was trustworthy.
            adjusted = b <= a
            if adjusted:
                b = a + 0.01
            entry = {"word": token, "start": round(a, 3), "end": round(b, 3)}
            if adjusted:
                entry["timing_estimated"] = True
            if getattr(word, "probability", None) is not None:
                entry["probability"] = round(float(word.probability), 4)
            tokens.append(entry)

        if not tokens:
            warnings.append("ASR segment did not provide word timestamps")
            cues.append({"start": round(start, 3), "end": round(end, 3),
                         "text": text, "words": []})
            continue

        chunk = []
        def flush():
            if not chunk: return
            cues.append({
                "start": chunk[0]["start"], "end": chunk[-1]["end"],
                "text": _text([w["word"] for w in chunk]),
                "words": list(chunk)})
            chunk.clear()

        for word in tokens:
            if chunk and (word["end"] - chunk[0]["start"] > max_duration or
                          len(_text([w["word"] for w in chunk]+[word["word"]])) > max_chars):
                flush()
            chunk.append(word)
            if END_PUNCT.search(word["word"]) and word["end"]-chunk[0]["start"] >= 0.8:
                flush()
        flush()

    cues.sort(key=lambda item: (item["start"], item["end"]))
    valid, prev_end = [], 0.0
    for cue in cues:
        if cue["start"] < prev_end:
            if prev_end-cue["start"] > .25:
                warnings.append("ASR segments overlapped; cue boundaries were clamped")
            cue["start"] = round(prev_end, 3)
        if cue["start"] >= cue["end"]:
            warnings.append("Dropped an overlapping cue")
            continue
        cue["id"] = len(valid)+1
        valid.append(cue)
        prev_end = cue["end"]
    return valid, sorted(set(warnings))


class FasterWhisper(StageProvider):
    def run(self, context: dict) -> dict:
        from faster_whisper import WhisperModel

        cfg = context["config"].get("whisper", {})
        model_name = cfg.get("model", "small.en")
        device = cfg.get("device", "cpu")
        compute_type = cfg.get("compute_type", "int8")
        model = WhisperModel(model_name, device=device, compute_type=compute_type)
        ingest = context["previous"]["ingest"]
        audio = ingest.get("vocals") or ingest.get("audio")
        if not audio:
            raise ValueError("Ingest stage has no audio; rerun Stage 1")

        # original-mix is intentional when Demucs separation was skipped or blocked
        audio_kind = "separated_vocals" if ingest.get("no_vocals") else "original_mixed_audio"

        segments, info = model.transcribe(
            audio,
            beam_size=int(cfg.get("beam_size", 5)),
            language="en",
            word_timestamps=True,
            vad_filter=bool(cfg.get("vad_filter", True)),
            condition_on_previous_text=False)

        data, warnings = _segments_to_cues(
            segments,
            max_duration=float(cfg.get("max_caption_seconds", 6.0)),
            max_chars=int(cfg.get("max_caption_chars", 84)))
        if not data:
            raise ValueError("No English speech detected")
        if not any(cue["words"] for cue in data):
            raise ValueError("ASR returned no usable word timestamps")
        words = sum(len(cue["words"]) for cue in data)
        adjusted_words = sum(
            1 for cue in data for word in cue["words"]
            if word.get("timing_estimated"))
        if adjusted_words:
            warnings.append(
                f"{adjusted_words} zero-length word timestamps were preserved with 10ms estimates")
        if audio_kind == "original_mixed_audio":
            warnings.append("Transcribed mixed original audio: Demucs vocals were unavailable")
        if any(not cue["words"] for cue in data):
            warnings.append("Some captions lack word timestamps; review output")
        out = Path(context["folder"])/"transcribe"
        out.mkdir(parents=True, exist_ok=True)
        english_json = out/"english.json"
        english_srt = out/"english.srt"
        report_path = out/"asr_report.json"
        payload = {
            "language": "en",
            "requested_language": "en",
            "detected_language": getattr(info, "language", None),
            "model": model_name,
            "audio_kind": audio_kind,
            "segments": data}
        english_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
        write_srt(data, english_srt)
        report = {
            "stage": "transcribe",
            "status": "completed",
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "model": model_name,
            "device": device,
            "compute_type": compute_type,
            "language": "en",
            "audio_kind": audio_kind,
            "captions": len(data),
            "words_with_timestamps": words,
            "estimated_zero_length_word_timings": adjusted_words,
            "start_s": data[0]["start"],
            "end_s": data[-1]["end"],
            "warnings": sorted(set(warnings)),
            "transcription_reviewed_by_human": False
        }
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
        return {
            "english_json": str(english_json),
            "english_srt": str(english_srt),
            "asr_report": str(report_path),
            "segments": len(data),
            "word_count": words,
            "audio_kind": audio_kind}
