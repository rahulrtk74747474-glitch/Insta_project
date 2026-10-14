"""Resumable stage runner with provider swapping."""
from __future__ import annotations
import hashlib,logging
from pathlib import Path
from .common import STAGES
from .db import JobDB
from .ingest import YtDlpOrFile
from .transcribe import FasterWhisper
from .transcribe_improved import ImprovedFasterWhisper
from .translate import OpenAIHindiTranslator
from .translate_spoken import NaturalHindiScriptAdapter
from .voice import OpenAIHindiVoice

PROVIDERS={"ingest":YtDlpOrFile,"transcribe":ImprovedFasterWhisper,"translate":OpenAIHindiTranslator,"voice":OpenAIHindiVoice}

class Pipeline:
    def __init__(self,config,providers=None):
        self.config=config
        self.root=Path(config.get("output_dir","output")).resolve();self.root.mkdir(parents=True,exist_ok=True)
        self.db=JobDB(Path(config.get("database","state/jobs.sqlite3")))
        self.providers=providers if providers is not None else {s:provider() for s,provider in PROVIDERS.items()}
        if providers is None:
            selected = config.get("whisper", {}).get("provider", "improved")
            if selected == "original":
                self.providers["transcribe"] = FasterWhisper()
            elif selected == "improved":
                self.providers["transcribe"] = ImprovedFasterWhisper()
            else:
                raise ValueError(f"Unknown whisper.provider: {selected!r}; choose improved or original")
        if providers is None:
            mode = config.get("translation", {}).get("mode", "spoken_adaptation")
            if mode == "spoken_adaptation":
                self.providers["translate"] = NaturalHindiScriptAdapter()
            elif mode == "subtitle_literal":
                self.providers["translate"] = OpenAIHindiTranslator()
            else:
                raise ValueError(f"Unknown translation.mode: {mode!r}")
        self.log=logging.getLogger("hindi_pipeline")
    @staticmethod
    def identifier(source,mode):
        value=str(Path(source).expanduser().resolve()) if mode=="local" else source
        return hashlib.sha256((mode+"\0"+value).encode()).hexdigest()[:16]
    def create(self,source,mode,rights_confirmed):
        if not rights_confirmed:raise PermissionError("Pass --rights-confirmed for content you own or have rights to use")
        if mode=="local" and not Path(source).expanduser().is_file():raise FileNotFoundError(source)
        resolved=str(Path(source).expanduser().resolve()) if mode=="local" else source
        id=self.identifier(resolved,mode)
        self.db.add(id,resolved,mode)
        return id
    @staticmethod
    def valid(result):
        if not result:return False
        paths=("video","audio","vocals","no_vocals","english_srt","english_json","asr_report","hindi_srt","hindi_json","translation_report","hindi_voice_script_json","hindi_voice_script_txt","hindi_voice_wav","voice_report","hindi_tts_estimated_srt","hindi_tts_estimated_json")
        return all(not isinstance(v,str) or k not in paths or Path(v).is_file() for k,v in result.items())
    def process(self,id,until="translate",force_stage=None):
        if until not in STAGES:raise ValueError("Unsupported stage")
        job=self.db.job(id)
        out=self.root/id;out.mkdir(parents=True,exist_ok=True)
        previous={};forced=False
        for stage in STAGES[:STAGES.index(until)+1]:
            if stage==force_stage:forced=True
            state=self.db.stage(id,stage)
            is_current = True
            # Do not incorrectly reuse previously translated files if English text,
            # target model, glossary, or timing settings have changed.
            if stage in ("translate","voice") and not forced and state["status"] == "completed":
                provider = self.providers[stage]
                if hasattr(provider, "fingerprint"):
                    expected = provider.fingerprint({
                        "job_id": id, "folder": str(out), "source": job["source"],
                        "source_type": job["source_type"], "config": self.config,
                        "previous": previous,
                    })
                    is_current = bool(state["result"] and state["result"].get("fingerprint") == expected)
            if not forced and is_current and state["status"]=="completed" and self.valid(state["result"]):
                previous[stage]=state["result"]
                self.log.info("stage.skipped",extra={"job_id":id,"stage":stage})
                continue
            # Rebuild any downstream stage when upstream artifacts changed.
            forced=True
            self.db.start(id,stage)
            self.log.info("stage.started",extra={"job_id":id,"stage":stage})
            try:
                context={"job_id":id,"folder":str(out),"source":job["source"],"source_type":job["source_type"],
                         "config":self.config,"previous":previous}
                result=self.providers[stage].run(context)
                if not self.valid(result):raise RuntimeError(f"Missing stage artifact for {stage}")
                self.db.finish(id,stage,result);previous[stage]=result
                self.log.info("stage.completed",extra={"job_id":id,"stage":stage})
            except Exception as exc:
                self.db.fail(id,stage,exc)
                self.log.exception("stage.failed",extra={"job_id":id,"stage":stage})
                raise
        return {"job_id":id,"output":str(out),"stages":self.db.stages(id)}
