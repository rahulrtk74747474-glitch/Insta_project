"""Integration smoke: download tiny.en in GitHub Actions, transcribe generated speech."""
from __future__ import annotations
import json
import subprocess
import tempfile
from pathlib import Path
from hindi_pipeline.transcribe import FasterWhisper

def main():
    phrase="Study a little every day. Review your notes and test your memory."
    with tempfile.TemporaryDirectory() as temp:
        root=Path(temp)
        audio=root/"synthetic_english.wav"
        subprocess.run(["espeak","-v","en-us","-s","130","-w",str(audio),phrase],check=True)
        result=FasterWhisper().run({
            "folder":str(root),
            "config":{"whisper":{"model":"tiny.en","device":"cpu",
               "compute_type":"int8","beam_size":2,"vad_filter":False}},
            "previous":{"ingest":{"audio":str(audio),"vocals":str(audio),"no_vocals":None}}})
        report=json.loads(Path(result["asr_report"]).read_text(encoding="utf-8"))
        print(json.dumps(report,ensure_ascii=False,indent=2))
        assert report["captions"]>0 and report["words_with_timestamps"]>0
        assert Path(result["english_srt"]).stat().st_size>0

if __name__=="__main__":
    main()
