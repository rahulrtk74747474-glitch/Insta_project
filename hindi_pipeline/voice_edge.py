"""Stage 4 non-cloning Hindi neural voice provider.

Uses the open-source edge-tts Python client with hi-IN-MadhurNeural.
No eSpeak, no user recording, and no ChatGPT conversation. Requires an
external Microsoft speech service reachable from this machine. Subject to
Microsoft's service terms and availability; not an offline TTS solution.
"""
from __future__ import annotations
import asyncio
import os
from pathlib import Path
from .common import command
from .voice import OpenAIHindiVoice

class EdgeHindiVoice(OpenAIHindiVoice):
    provider_name="edge"
    def __init__(self):
        super().__init__()
        self.settings={}
    def run(self,context):
        self.settings=context["config"].get("voice",{})
        return super().run(context)
    def _synthesize(self,text,output,model,voice,instructions):
        if not voice.startswith("hi-IN-") or not voice.endswith("Neural"):
            raise ValueError("EdgeHindiVoice requires a Hindi hi-IN-...Neural voice")
        rate=self.settings.get("rate","-2%")
        if not isinstance(rate,str) or not __import__("re").fullmatch(r"[+-]?\d{1,2}%",rate):
            raise ValueError("Edge TTS rate must be a string like '-2%' or '+5%'")
        try:
            import edge_tts
        except ImportError as exc:
            raise RuntimeError("Install edge-tts to enable Hindi neural speech") from exc
        mp3=output.with_suffix(".edge-tmp.mp3")
        try:
            asyncio.run(edge_tts.Communicate(text,voice=voice,rate=rate).save(str(mp3)))
            if not mp3.is_file() or mp3.stat().st_size<800:
                raise RuntimeError("The Hindi neural speech service returned empty audio")
            command(["ffmpeg","-hide_banner","-loglevel","error","-y",
                     "-i",str(mp3),"-vn","-ar","24000","-ac","1",
                     "-c:a","pcm_s16le",str(output)])
            if not output.is_file() or output.stat().st_size<44:
                raise RuntimeError("Could not decode Hindi neural MP3 to 24k WAV")
        finally:
            mp3.unlink(missing_ok=True)
