"""Stage 5: authorized video + Hindi narration -> reviewable MP4 variants.

Never maps the original video's English audio. No uploader, scheduler, or social API.
Subtitles are estimated within measured TTS idea blocks, NOT word-level forced alignment.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .common import StageProvider, command, probe
from .translate import _write_atomic

REVISION = "stage5-render-v1"


def _dimensions(data):
    if not isinstance(data, (list, tuple)) or len(data) != 2:
        raise ValueError("render dimensions must contain width and height")
    width, height = (int(x) for x in data)
    if not all(64 <= x <= 3840 and x % 2 == 0 for x in (width, height)):
        raise ValueError("render dimensions must be even and between 64 and 3840")
    return width, height


def _read_inputs(context):
    previous = context["previous"]
    source = previous.get("ingest", {}).get("video")
    narration = previous.get("voice", {}).get("hindi_voice_wav")
    captions = previous.get("voice", {}).get("hindi_tts_estimated_srt")
    if not source or not narration:
        raise ValueError("Stage 5 requires completed ingestion and Stage 4 Hindi narration WAV")
    source, narration = Path(source), Path(narration)
    if not source.is_file() or not narration.is_file():
        raise FileNotFoundError("Source video or Hindi voice WAV missing")
    return previous, source, narration, Path(captions) if captions else None


def _fingerprint(context):
    previous, video, voice, subtitles = _read_inputs(context)
    cfg = context["config"].get("render", {})
    def stat(p):
        if p is None or not p.is_file():
            return None
        info = p.stat()
        return {"size": info.st_size, "mtime_ns": info.st_mtime_ns}
    payload = {
        "revision": REVISION,
        "config": cfg,
        "ingest": previous.get("ingest", {}).get("duration"),
        "voice_fingerprint": previous.get("voice", {}).get("fingerprint"),
        "files": {
            "video": str(video.resolve()), "video_stat": stat(video),
            "voice": str(voice.resolve()), "voice_stat": stat(voice),
            "subtitles": str(subtitles.resolve()) if subtitles else None,
            "subtitle_stat": stat(subtitles),
        },
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()


def _video_filter(width, height, crop_mode, srt, font_name, font_size, margin_v):
    if crop_mode == "fit":
        scale = f"scale={width}:{height}:force_original_aspect_ratio=decrease"
        transform = f"{scale},pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black"
    elif crop_mode == "fill":
        transform = (f"scale={width}:{height}:force_original_aspect_ratio=increase,"
                     f"crop={width}:{height}")
    else:
        raise ValueError("render.portrait_mode must be 'fit' or 'fill'")
    parts=[transform,"setsar=1"]
    if srt is not None:
        if not re.fullmatch(r"[A-Za-z0-9 -]{1,60}",font_name):
            raise ValueError("Unsafe font name: only letters/numbers/spaces/hyphens")
        # srt lives in a newly-created, safe ASCII Linux temp folder.
        # force_style inside quotes allows commas in the libass style.
        style=(f"FontName={font_name},FontSize={font_size},"
               "PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,"
               f"Outline=2,Shadow=0,MarginV={margin_v},Alignment=2")
        parts.append(f"subtitles=filename={srt}:force_style='{style}'")
    return ",".join(parts)


def _output_info(path, width, height, expected_duration):
    if not path.is_file() or path.stat().st_size < 1024:
        raise ValueError("FFmpeg did not produce nonempty rendered MP4")
    raw=probe(path)
    v=next((x for x in raw["streams"] if x.get("codec_type")=="video"),None)
    a=next((x for x in raw["streams"] if x.get("codec_type")=="audio"),None)
    if not v or not a:
        raise ValueError("Rendered MP4 is missing video or Hindi audio stream")
    if (v.get("width"),v.get("height"))!=(width,height):
        raise ValueError("Rendered MP4 has incorrect dimensions")
    duration=float(raw["format"]["duration"])
    if not math.isfinite(duration) or abs(duration-expected_duration)>.45:
        raise ValueError(f"Rendered MP4 duration {duration:.3f}s differs from source {expected_duration:.3f}s")
    if v.get("codec_name")!="h264" or a.get("codec_name")!="aac":
        raise ValueError("Expected H.264 video and AAC narration audio")
    return {"path":str(path),"width":width,"height":height,
            "duration_seconds":round(duration,3),
            "video_codec":v["codec_name"],"audio_codec":a["codec_name"],
            "bytes":path.stat().st_size}


class HindiVideoComposer(StageProvider):
    """Produce both 16:9 source-context MP4 and 9:16 social-format MP4, locally."""

    @staticmethod
    def fingerprint(context):
        return _fingerprint(context)

    def run(self, context: dict[str, Any]) -> dict[str, Any]:
        previous, video, voice, subtitles = _read_inputs(context)
        config=context["config"].get("render",{})
        landscape=_dimensions(config.get("landscape", [1280,720]))
        portrait=_dimensions(config.get("portrait", [720,1280]))
        portrait_mode=config.get("portrait_mode","fit")
        if portrait_mode not in ("fit","fill"):
            raise ValueError("render.portrait_mode must be fit or fill")
        fps=int(config.get("fps",30))
        if not 12 <= fps <= 60:
            raise ValueError("render.fps must be 12..60")
        crf=int(config.get("crf",23))
        if not 16 <= crf <= 32:
            raise ValueError("render.crf must be 16..32")
        preset=config.get("preset","veryfast")
        if preset not in ("ultrafast","superfast","veryfast","faster","fast","medium","slow"):
            raise ValueError("Unsupported render.preset")
        burn=bool(config.get("burn_subtitles",True))
        font_name=config.get("subtitle_font","Noto Sans Devanagari")
        if not isinstance(font_name,str) or not re.fullmatch(r"[A-Za-z0-9 -]{1,60}",font_name):
            raise ValueError("Unsafe render.subtitle_font")
        font_size=int(config.get("subtitle_font_size",24))
        if not 8<=font_size<=64:
            raise ValueError("render.subtitle_font_size must be 8..64")
        background_on=bool(config.get("mix_separated_background",False))
        background_level=float(config.get("background_volume",0.12))
        if not 0 <= background_level <= .5:
            raise ValueError("background_volume must be in 0..0.5")
        stem=previous.get("ingest",{}).get("no_vocals")
        if background_on and (not stem or not Path(stem).is_file()):
            raise ValueError("Background mix requested, but isolated no_vocals.wav is missing. "
                             "Do not mix original English audio into the Hindi dub.")
        if burn and (subtitles is None or not subtitles.is_file()):
            raise ValueError("Burn-in requested but Stage 4 estimated Hindi SRT is missing")
        srci=probe(video)
        duration=float(srci["format"]["duration"])
        audi=probe(voice)
        audio_duration=float(audi["format"]["duration"])
        if not math.isfinite(duration) or duration<=0:
            raise ValueError("Invalid source video duration")
        if abs(audio_duration-duration)>.45:
            raise ValueError("Hindi voice must already be aligned to the source video timeline")
        if not any(x.get("codec_type")=="video" for x in srci["streams"]):
            raise ValueError("No source video stream")

        out=Path(context["folder"])/"render"
        out.mkdir(parents=True,exist_ok=True)
        signature=_fingerprint(context)
        result={}
        reports={}
        # Use safe temp filenames: FFmpeg's subtitle filter has multiple quoting layers.
        # Never expose original user-controlled paths directly in filter expressions.
        with tempfile.TemporaryDirectory(prefix="hi_stage5_") as temporary:
            tmp=Path(temporary)
            subtitle_path=None
            if burn:
                subtitle_path=tmp/"captions.srt"
                shutil.copy2(subtitles,subtitle_path)
                filter_list=command(["ffmpeg","-hide_banner","-filters"])
                if " subtitles " not in filter_list:
                    raise RuntimeError("FFmpeg libass 'subtitles' filter unavailable. Install FFmpeg with libass.")
            for variant, dims, mode in (
                ("landscape",landscape,"fit"),
                ("portrait",portrait,portrait_mode),
            ):
                w,h=dims
                target=out/f"hindi_{variant}.mp4"
                partial=out/f".hindi_{variant}.partial.mp4"
                partial.unlink(missing_ok=True)
                filt=_video_filter(w,h,mode,subtitle_path,font_name,font_size,
                                   55 if variant=="landscape" else 90)
                args=["ffmpeg","-hide_banner","-loglevel","error","-y",
                      "-i",str(video),"-i",str(voice)]
                if background_on:
                    args.extend(["-i",str(Path(stem))])
                args.extend(["-map","0:v:0"])
                if background_on:
                    # Original English audio (0:a) is intentionally NOT mapped.
                    args.extend(["-filter_complex",
                                 f"[1:a]volume=1[dub];[2:a]volume={background_level:.4f}[bg];"
                                 "[dub][bg]amix=inputs=2:duration=first:dropout_transition=0[hi]",
                                 "-map","[hi]"])
                else:
                    args.extend(["-map","1:a:0"])
                args.extend([
                    "-vf",filt,"-r",str(fps),
                    "-c:v","libx264","-preset",preset,"-crf",str(crf),
                    "-pix_fmt","yuv420p",
                    "-c:a","aac","-b:a","128k",
                    "-t",f"{duration:.6f}",
                    "-movflags","+faststart","-metadata","comment=Hindi dub - manual review only",
                    str(partial)])
                try:
                    command(args,timeout=7200)
                    validated=_output_info(partial,w,h,duration)
                    os.replace(partial,target)
                except Exception:
                    partial.unlink(missing_ok=True)
                    raise
                validated["path"]=str(target)
                reports[variant]=validated
                result[variant]=str(target)
        review=out/"render_report.json"
        report={
            "stage":"render","status":"completed",
            "generated_at_utc":datetime.now(timezone.utc).isoformat(),
            "fingerprint":signature,"source_video":str(video),
            "hindi_voice":str(voice),
            "original_english_audio_included":False,
            "background_from_demucs_only":background_on,
            "background_volume":background_level if background_on else 0,
            "burned_in_hindi_subtitles":burn,
            "subtitle_alignment":"estimated_inside_measured_block_not_word_aligned" if burn else "not_embedded",
            "portrait_mode":portrait_mode,
            "outputs":reports,
            "warnings":[
                "Subtitle times are estimates, not word-for-word speech synchronization.",
                "Portrait fit preserves the full source image with padding; fill mode crops edges.",
                "No render is published automatically. Manual review and publishing only.",
                "Real Hindi accent and narration accuracy still require human review."
            ],
        }
        _write_atomic(review,json.dumps(report,ensure_ascii=False,indent=2)+"\n")
        return {"hindi_landscape_mp4":result["landscape"],
                "hindi_portrait_mp4":result["portrait"],
                "render_report":str(review),
                "fingerprint":signature,
                "manual_publish_only":True}
