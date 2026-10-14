"""Provider contract, safe command wrapper, structured logging, subtitles."""
from __future__ import annotations
from abc import ABC, abstractmethod
import json, logging, math, re, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

STAGES=("ingest","transcribe","translate")

class StageProvider(ABC):
    @abstractmethod
    def run(self,context:dict[str,Any])->dict[str,Any]:
        """Return JSON-serializable stage result."""

class JSONFormatter(logging.Formatter):
    def format(self,record):
        item={"time":datetime.now(timezone.utc).isoformat(),"level":record.levelname,"event":record.getMessage()}
        for field in ("job_id","stage","attempt"):
            if hasattr(record,field):item[field]=getattr(record,field)
        if record.exc_info:item["error"]=self.formatException(record.exc_info)
        return json.dumps(item,ensure_ascii=False)

def setup_logging():
    root=logging.getLogger();root.handlers.clear()
    h=logging.StreamHandler(sys.stderr);h.setFormatter(JSONFormatter())
    root.addHandler(h);root.setLevel(logging.INFO)

def command(argv:list[str],timeout:int=7200)->str:
    p=subprocess.run(argv,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=timeout,check=False)
    if p.returncode:
        raise RuntimeError(f"Command {Path(argv[0]).name} failed ({p.returncode}): {p.stderr[-1600:]}")
    return p.stdout.strip()

def probe(path:Path)->dict:
    return json.loads(command(["ffprobe","-v","error","-show_format","-show_streams","-of","json",str(path)]))

def hms(seconds:float)->str:
    ms=round(max(0,seconds)*1000)
    h,r=divmod(ms,3600000);m,r=divmod(r,60000);s,ms=divmod(r,1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

def write_srt(entries:list[dict],dest:Path):
    blocks=[]
    for i,item in enumerate(entries,1):
        a,b=float(item["start"]),float(item["end"])
        if not(math.isfinite(a) and math.isfinite(b) and 0<=a<b):raise ValueError("Invalid subtitle timing")
        value=re.sub(r"[\r\n]+"," ",str(item["text"])).strip()
        if not value:raise ValueError("Empty subtitle")
        blocks.append(f"{i}\n{hms(a)} --> {hms(b)}\n{value}\n")
    dest.write_text("\n".join(blocks)+"\n",encoding="utf-8")
