"""Improved English ASR provider: base.en + readable subtitle cue optimization."""
from __future__ import annotations
import json
import math
from datetime import datetime, timezone
from pathlib import Path

from .common import StageProvider
from .caption_optimizer import optimize, metrics, save_srt


class ImprovedFasterWhisper(StageProvider):
    def run(self, context):
        from faster_whisper import WhisperModel
        settings = context["config"].get("whisper", {})
        model_name = settings.get("model", "base.en")
        model = WhisperModel(model_name,
                             device=settings.get("device", "cpu"),
                             compute_type=settings.get("compute_type", "int8"))
        ingest = context["previous"]["ingest"]
        audio = ingest.get("vocals") or ingest.get("audio")
        if not audio:
            raise ValueError("No audio from Stage 1")

        separated = bool(ingest.get("no_vocals"))
        audio_kind = "separated_vocals" if separated else "original_mixed_audio"
        raw, info = model.transcribe(
            audio,
            beam_size=int(settings.get("beam_size", 4)),
            language="en", word_timestamps=True,
            vad_filter=bool(settings.get("vad_filter", True)),
            condition_on_previous_text=False,
        )
        items=[]
        for segment in raw:
            if not str(segment.text).strip() or segment.end <= segment.start:
                continue
            items.append({
                "start":round(float(segment.start),3),
                "end":round(float(segment.end),3),
                "text":str(segment.text).strip(),
                "words":[{
                    "start":round(float(word.start),3),
                    "end":round(float(word.end),3),
                    "word":str(word.word).strip(),
                    "probability":round(float(word.probability),4)
                        if getattr(word,"probability",None) is not None else None,
                } for word in (segment.words or [])
                  if word.start is not None and word.end is not None]
            })
        if not items:
            raise ValueError("No English speech was recognized")
        media_duration=ingest.get("duration")
        cues, repair_info=optimize({"segments":items},
                                  media_duration=float(media_duration) if media_duration else None)
        quality=metrics(cues)
        if not cues:
            raise ValueError("No usable word-level timestamps")
        output=Path(context["folder"])/"transcribe"
        output.mkdir(parents=True,exist_ok=True)
        english_json=output/"english.json"
        english_srt=output/"english.srt"
        report_file=output/"asr_report.json"
        english_json.write_text(
            json.dumps({
                "language":"en","requested_language":"en",
                "detected_language":getattr(info,"language",None),
                "model":model_name,"audio_kind":audio_kind,
                "raw_segments":len(items),
                "segments":cues
            },ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
        save_srt(cues, english_srt)
        warnings=[]
        if not separated:
            warnings.append("Transcribed original mixed audio: Demucs isolated vocals unavailable")
        if repair_info["timing_repairs"]:
            warnings.append(f"{repair_info['timing_repairs']} zero-duration word timestamps estimated; inspect marked words")
        if quality["cps_over_18"]:
            warnings.append(f"{quality['cps_over_18']} subtitle cues still exceed 18 characters/s")
        report={
            "stage":"transcribe","status":"completed",
            "created_at_utc":datetime.now(timezone.utc).isoformat(),
            "model":model_name,
            "device":settings.get("device","cpu"),
            "compute_type":settings.get("compute_type","int8"),
            "audio_kind":audio_kind,
            "raw_asr_segments":len(items),
            "word_count":quality["words"],
            "raw_word_timing_repairs":repair_info["timing_repairs"],
            "subtitle_metrics":quality,
            "warnings":warnings,
            "transcription_reviewed_by_human":False,
            "wer_measured":False,
        }
        report_file.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
        return {
            "english_json":str(english_json),
            "english_srt":str(english_srt),
            "asr_report":str(report_file),
            "segments":len(cues),
            "word_count":quality["words"],
            "audio_kind":audio_kind,
            "provider":"faster-whisper-optimized",
        }
