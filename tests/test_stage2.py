"""Stage 2 unit tests: no ASR model download required."""
from __future__ import annotations
import json, sys, tempfile, unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from hindi_pipeline.transcribe import FasterWhisper, _segments_to_cues

def word(a,b,text):
    return SimpleNamespace(start=a,end=b,word=text,probability=.97)
def seg(a,b,text,words):
    return SimpleNamespace(start=a,end=b,text=text,words=words)

class WordTimingTests(unittest.TestCase):
    def test_punctuation_creates_readable_captions(self):
        raw=[seg(0,3,"Hello world. Let's start.",[
            word(.2,.6,"Hello"),word(.7,1.1,"world."),
            word(1.2,1.7,"Let's"),word(1.8,2.2,"start.")])]
        cues,warnings=_segments_to_cues(raw,6,84)
        self.assertEqual([x["text"] for x in cues],["Hello world.","Let's start."])
        self.assertEqual(cues[1]["start"],1.2)
        self.assertEqual(cues[1]["words"][0]["probability"],.97)
        self.assertEqual(warnings,[])

    def test_long_caption_splits_on_duration(self):
        raw=[seg(0,8,"one two three four",[
            word(.1,1,"one"),word(1.2,2.3,"two"),word(4,5.1,"three"),word(7,8,"four")])]
        cues,_=_segments_to_cues(raw,4,84)
        self.assertEqual(len(cues),2)
        self.assertEqual(cues[1]["text"],"three four")

    def test_overlapping_cues_clamped(self):
        raw=[seg(0,2,"first", [word(0,2,"first")]),
             seg(1.9,3,"second", [word(1.9,3,"second")])]
        cues,warnings=_segments_to_cues(raw,6,84)
        self.assertEqual(cues[1]["start"],2.0)
        self.assertEqual(len(warnings),0)

    def test_zero_length_timestamp_preserves_word(self):
        cues, warnings = _segments_to_cues(
            [seg(0, 2, "Feel productive.", [
                word(.2, .2, "Feel"), word(.3, 1.1, "productive.")])], 6, 84)
        self.assertEqual(cues[0]["text"], "Feel productive.")
        self.assertEqual(cues[0]["words"][0]["end"], .21)
        self.assertTrue(cues[0]["words"][0]["timing_estimated"])
        self.assertEqual(warnings, [])

    def test_empty_word_list_warning(self):
        cues,warnings=_segments_to_cues([seg(0,2,"Testing",[])],6,84)
        self.assertEqual(cues[0]["text"],"Testing")
        self.assertIn("ASR segment did not provide word timestamps",warnings)

class ProviderTests(unittest.TestCase):
    def test_provider_creates_english_srt_and_report(self):
        with tempfile.TemporaryDirectory() as td:
            model=MagicMock()
            model.transcribe.return_value=(
                [seg(0,2,"The sky is blue.",[word(.1,.4,"The"),word(.5,.8,"sky"),
                 word(.9,1.1,"is"),word(1.3,1.9,"blue.")])],
                SimpleNamespace(language="en"))
            with patch.dict(sys.modules,{"faster_whisper":
                SimpleNamespace(WhisperModel=lambda *args,**kwargs:model)}):
                result=FasterWhisper().run({
                    "folder":td,"config":{"whisper":{"model":"tiny.en"}},
                    "previous":{"ingest":{"audio":"/fake.wav","vocals":"/fake.wav","no_vocals":None}}})
            self.assertTrue(Path(result["english_srt"]).is_file())
            self.assertIn("The sky is blue.",Path(result["english_srt"]).read_text())
            output=json.loads(Path(result["english_json"]).read_text())
            self.assertEqual(output["segments"][0]["words"][2]["word"],"is")
            report=json.loads(Path(result["asr_report"]).read_text())
            self.assertEqual(report["words_with_timestamps"],4)
            self.assertEqual(report["audio_kind"],"original_mixed_audio")
            self.assertFalse(report["transcription_reviewed_by_human"])
            self.assertTrue(model.transcribe.call_args.kwargs["word_timestamps"])
            self.assertEqual(model.transcribe.call_args.kwargs["language"],"en")

    def test_missing_all_word_timestamps_fails_loudly(self):
        with tempfile.TemporaryDirectory() as td:
            model=MagicMock();model.transcribe.return_value=(
                [seg(0,2,"Testing",[])],SimpleNamespace(language="en"))
            with patch.dict(sys.modules,{"faster_whisper":
                SimpleNamespace(WhisperModel=lambda *args,**kwargs:model)}):
                with self.assertRaisesRegex(ValueError,"word timestamps"):
                    FasterWhisper().run({"folder":td,"config":{},
                        "previous":{"ingest":{"audio":"/fake.wav"}}})
if __name__=="__main__":
    unittest.main()
