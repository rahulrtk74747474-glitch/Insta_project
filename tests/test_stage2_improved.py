"""Offline tests for improved Stage 2. No model download or API credentials."""
from __future__ import annotations
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock,patch

from hindi_pipeline.caption_optimizer import optimize,metrics,save_srt
from hindi_pipeline.transcribe_improved import ImprovedFasterWhisper
from hindi_pipeline.orchestrator import Pipeline

def w(t,u,x):
    return {"start":t,"end":u,"word":x,"probability":0.95}

class OptimizerTest(unittest.TestCase):
    def test_all_words_preserved_and_no_subtitle_overlap(self):
        data={"segments":[{"words":[w(i*.42,i*.42+.35,f"word{i}") for i in range(30)]}]}
        cues,process=optimize(data,media_duration=15)
        self.assertEqual(sum(len(c["words"]) for c in cues),30)
        self.assertEqual(process["input_words"],30)
        self.assertFalse(any(cues[i]["start"]<cues[i-1]["end"] for i in range(1,len(cues))))
        self.assertTrue(all(c["start"]<c["end"] for c in cues))
        self.assertEqual(metrics(cues)["max_line_chars"]<=42,True)

    def test_zero_duration_flagged_not_omitted(self):
        cues,report=optimize({"segments":[{"words":[w(.1,.1,"Hello"),w(.5,.8,"world.")]}]},1)
        self.assertEqual(report["timing_repairs"],1)
        self.assertTrue(cues[0]["words"][0]["timing_estimated"])

    def test_line_wrap_in_srt(self):
        words=[w(i*.4,i*.4+.33,t) for i,t in enumerate(
            "Remember every concept by repeating it after a few days of studying together".split())]
        cues,_=optimize({"segments":[{"words":words}]},5.5)
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/"out.srt"
            save_srt(cues,p)
            self.assertIn("-->",p.read_text())
        self.assertEqual(metrics(cues)["words"],len(words))

    def test_empty_transcript_rejected(self):
        with self.assertRaisesRegex(ValueError,"No usable word"):
            optimize({"segments":[]})

class ProviderTest(unittest.TestCase):
    def test_provider_and_asr_report(self):
        ww=[SimpleNamespace(start=i*.48,end=i*.48+.39,word=txt,probability=.92)
             for i,txt in enumerate("You can learn with a better study routine.".split())]
        seg=SimpleNamespace(start=0.,end=3.3,text="You can learn with a better study routine.",words=ww)
        fake=MagicMock()
        fake.transcribe.return_value=([seg],SimpleNamespace(language="en"))
        with tempfile.TemporaryDirectory() as td:
            ctx={"folder":td,"config":{"whisper":{"model":"base.en"}},
                 "previous":{"ingest":{"audio":"/audio.wav","duration":4.0,"no_vocals":None}}}
            with patch.dict(sys.modules,{"faster_whisper":
                SimpleNamespace(WhisperModel=lambda *args,**kwargs:fake)}):
                result=ImprovedFasterWhisper().run(ctx)
            report=json.loads(Path(result["asr_report"]).read_text())
            self.assertEqual(report["model"],"base.en")
            self.assertEqual(report["word_count"],8)
            self.assertEqual(report["audio_kind"],"original_mixed_audio")
            self.assertFalse(report["wer_measured"])
            self.assertEqual(result["provider"],"faster-whisper-optimized")
            self.assertTrue(Path(result["english_srt"]).exists())

    def test_provider_switching(self):
        with tempfile.TemporaryDirectory() as td:
            opts={"output_dir":str(Path(td)/"out"),"database":str(Path(td)/"db.sqlite")}
            base=Pipeline(opts)
            self.assertEqual(base.providers["transcribe"].__class__.__name__,"FasterWhisper")
            opts["whisper"]={"provider":"improved"}
            better=Pipeline(opts)
            self.assertEqual(better.providers["transcribe"].__class__.__name__,"ImprovedFasterWhisper")

if __name__=="__main__":
    unittest.main()
