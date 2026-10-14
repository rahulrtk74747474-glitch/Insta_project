"""Authorized URL/local file -> audio -> optional separated vocal/background WAVs."""
from __future__ import annotations
import shutil, sys
from pathlib import Path
from urllib.parse import urlparse
from .common import StageProvider,command,probe

class YtDlpOrFile(StageProvider):
    def run(self,context):
        folder=Path(context["folder"])/"ingest";folder.mkdir(parents=True,exist_ok=True)
        source=context["source"]
        if context["source_type"]=="local":
            path=Path(source).expanduser().resolve()
            if not path.is_file():raise FileNotFoundError(path)
            video=folder/("source"+path.suffix.lower())
            if path!=video:shutil.copy2(path,video)
        else:
            url=urlparse(source)
            if url.scheme not in ("http","https") or not url.hostname:raise ValueError("Expected HTTP(S) video URL")
            command([sys.executable,"-m","yt_dlp","--no-playlist","--no-progress","-f","bv*+ba/b",
                     "--merge-output-format","mp4","-o",str(folder/"source.%(ext)s"),source])
            matches=[p for p in folder.glob("source.*") if p.suffix.lower() in (".mp4",".mkv",".mov",".webm")]
            if len(matches)!=1:raise RuntimeError(f"Expected one source video, found {len(matches)}")
            video=matches[0]
        info=probe(video)
        if not any(x.get("codec_type")=="video" for x in info.get("streams",[])):raise ValueError("Video stream missing")
        if not any(x.get("codec_type")=="audio" for x in info.get("streams",[])):raise ValueError("Audio stream missing")
        audio=folder/"audio.wav"
        command(["ffmpeg","-y","-v","error","-i",str(video),"-vn","-ac","2","-ar","44100","-c:a","pcm_s16le",str(audio)])
        result={"video":str(video),"audio":str(audio),"duration":float(info["format"]["duration"])}
        settings=context["config"].get("demucs",{})
        if settings.get("enabled",True):
            model=settings.get("model","htdemucs")
            sep=folder/"stems"
            command([sys.executable,"-m","demucs","-n",model,"--two-stems=vocals","-o",str(sep),str(audio)])
            base=sep/model/audio.stem
            for name in ("vocals","no_vocals"):
                stem=base/f"{name}.wav"
                if not stem.is_file():raise FileNotFoundError(stem)
                result[name]=str(stem)
        else:
            result.update(vocals=str(audio),no_vocals=None,note="Separation disabled; vocals not isolated.")
        return result
