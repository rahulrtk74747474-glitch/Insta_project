"""English Whisper ASR with word-level timing."""
from __future__ import annotations
import json
from pathlib import Path
from .common import StageProvider,write_srt

class FasterWhisper(StageProvider):
    def run(self,context):
        from faster_whisper import WhisperModel
        cfg=context["config"].get("whisper",{})
        model=WhisperModel(cfg.get("model","small.en"),device=cfg.get("device","cpu"),compute_type=cfg.get("compute_type","int8"))
        audio=context["previous"]["ingest"]["vocals"]
        segments,info=model.transcribe(audio,beam_size=int(cfg.get("beam_size",5)),language="en",
                                       word_timestamps=True,vad_filter=bool(cfg.get("vad_filter",True)))
        data=[]
        for segment in segments:
            if segment.end<=segment.start or not segment.text.strip():continue
            data.append({"id":len(data)+1,"start":round(segment.start,3),"end":round(segment.end,3),
                         "text":segment.text.strip(),
                         "words":[{"start":round(w.start,3),"end":round(w.end,3),"word":w.word.strip()}
                                  for w in (segment.words or []) if w.start is not None and w.end is not None]})
        if not data:raise ValueError("No English speech detected")
        out=Path(context["folder"])/"transcribe";out.mkdir(exist_ok=True)
        j=out/"english.json";s=out/"english.srt"
        j.write_text(json.dumps({"language":"en","detected_language":getattr(info,"language",None),"segments":data},
                                ensure_ascii=False,indent=2),encoding="utf-8")
        write_srt(data,s)
        return {"english_json":str(j),"english_srt":str(s),"segments":len(data)}
