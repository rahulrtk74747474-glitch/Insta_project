"""Real-model integration test on *generated* English audio. Saves reviewable artifacts."""
from __future__ import annotations
import json
import shutil
import subprocess
from pathlib import Path
from hindi_pipeline.transcribe import FasterWhisper

def main():
    phrase="Study a little every day. Review your notes and test your memory."
    root=Path("dist/stage2_synthetic_smoke")
    if root.exists():shutil.rmtree(root)
    root.mkdir(parents=True)
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
    (root/"TEST_NOTES.txt").write_text(
        "Synthetic English speech created in GitHub Actions using eSpeak.\n"
        "Transcribed with faster-whisper tiny.en CPU/int8.\n"
        "This is not the user's original video and does not test Demucs.\n"
        "See transcribe/english.srt, english.json, asr_report.json.\n",
        encoding="utf-8")

if __name__=="__main__":
    main()
