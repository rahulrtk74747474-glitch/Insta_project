"""Stage 3 translation tests: all OpenAI responses mocked, no keys or billing."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from hindi_pipeline.translate import OpenAIHindiTranslator
from hindi_pipeline.translation_quality import (
    approximate_speech_seconds, check_english_segments, fingerprint,
    glossary_matches, validate_hindi,
)


def choice(items):
    return SimpleNamespace(choices=[SimpleNamespace(
        finish_reason="stop",
        message=SimpleNamespace(content=json.dumps({"items":items},ensure_ascii=False),refusal=None))])


class FakeChat:
    def __init__(self, responses):
        self.responses=list(responses)
        self.calls=[]
    def create(self,**kwargs):
        self.calls.append(kwargs)
        if not self.responses:raise RuntimeError("Unexpected API request")
        reply=self.responses.pop(0)
        if isinstance(reply,Exception):raise reply
        return reply


def client(fake):
    return SimpleNamespace(chat=SimpleNamespace(completions=fake))


class TestDeterministicChecks(unittest.TestCase):
    def test_time_invariants(self):
        data={"segments":[{"id":1,"start":0.0,"end":2.0,"text":"Hello."},
                          {"id":2,"start":2.1,"end":4.5,"text":"The answer."}]}
        src=check_english_segments(data)
        lines,quality=validate_hindi(src,[{"id":1,"text":"नमस्ते।"},{"id":2,"text":"यह जवाब है।"}],{})
        self.assertEqual(quality["problems"],[])
        self.assertEqual([x["start"] for x in src],[x["start"] for x in lines])
        self.assertEqual([x["end"] for x in src],[x["end"] for x in lines])
    def test_reject_dropped_or_reordered_ids(self):
        src=check_english_segments({"segments":[
            {"id":1,"start":0,"end":2,"text":"Hello"},{"id":2,"start":2,"end":4,"text":"World"}]})
        with self.assertRaisesRegex(ValueError,"changed, duplicated"):
            validate_hindi(src,[{"id":2,"text":"दुनिया"},{"id":1,"text":"नमस्ते"}],{})
    def test_reject_english_overlap(self):
        with self.assertRaisesRegex(ValueError,"Overlapping"):
            check_english_segments({"segments":[{"id":1,"start":0,"end":2,"text":"Hello"},
                                           {"id":2,"start":1.5,"end":3,"text":"World"}]})
    def test_glossary_is_word_bounded_and_case_insensitive(self):
        found=glossary_matches("Use Active Recall and techniques.",{"active recall":"एक्टिव रिकॉल","call":"कॉल"})
        self.assertEqual(found,{"active recall":"एक्टिव रिकॉल"})
    def test_long_hindi_requires_shortening(self):
        src=check_english_segments({"segments":[{"id":1,"start":0,"end":.7,"text":"Know it."}]})
        _,r=validate_hindi(src,[{"id":1,"text":"क्या आप पूरे संसार की सबसे जरूरी बात को ठीक से समझते हैं?"}],{})
        self.assertIn("Estimated spoken Hindi exceeds slot",[x["reason"] for x in r["problems"]])
    def test_devanagari_and_glossary_enforced(self):
        src=check_english_segments({"segments":[{"id":1,"start":0,"end":5,"text":"Use active recall"}]})
        _,result=validate_hindi(src,[{"id":1,"text":"Use active recall"}],{"active recall":"एक्टिव रिकॉल"})
        self.assertIn("Missing Hindi Devanagari text",[x["reason"] for x in result["problems"]])
        self.assertIn("Glossary term missing",[x["reason"] for x in result["problems"]])
    def test_config_changes_fingerprint(self):
        data={"segments":[{"id":1,"start":0,"end":3,"text":"Study"}]}
        self.assertNotEqual(fingerprint(data,"model1",{},8,1.15),
                            fingerprint(data,"model2",{},8,1.15))


class TestProvider(unittest.TestCase):
    def setUp(self):
        td=tempfile.TemporaryDirectory();self.addCleanup(td.cleanup)
        self.root=Path(td.name)
        self.english=self.root/"english.json"
        self.cfg={"translation":{"model":"gpt-4o-mini","batch_size":1,
                                "speed_tolerance":1.15,
                                "glossary":{"active recall":"एक्टिव रिकॉल"}}}
        self.data={"segments":[
            {"id":1,"start":0,"end":3,"text":"Practice active recall."},
            {"id":2,"start":3.1,"end":7.1,"text":"Study again tomorrow."},
        ]}
        self.english.write_text(json.dumps(self.data),encoding="utf-8")
        self.context={"config":self.cfg,"folder":str(self.root),
                      "previous":{"transcribe":{"english_json":str(self.english)}}}
    def test_hindi_srt_json_report_and_glossary(self):
        service=FakeChat([choice([{"id":1,"text":"एक्टिव रिकॉल का अभ्यास करें।"}]),
                          choice([{"id":2,"text":"कल फिर पढ़िए।"}])])
        result=OpenAIHindiTranslator(client(service)).run(self.context)
        self.assertEqual(result["segments"],2)
        text=Path(result["hindi_srt"]).read_text(encoding="utf-8")
        self.assertIn("एक्टिव रिकॉल",text)
        self.assertIn("00:00:03,100 --> 00:00:07,100",text)
        output=json.loads(Path(result["hindi_json"]).read_text(encoding="utf-8"))
        self.assertEqual(output["segments"][0]["end"],3)
        self.assertEqual(output["segments"][1]["start"],3.1)
        report=json.loads(Path(result["translation_report"]).read_text(encoding="utf-8"))
        self.assertEqual(report["number_of_cues"],2)
        self.assertTrue(report["cue_timestamps_preserved"])
        self.assertEqual(report["glossary_applied"],1)
        self.assertEqual(report["api_requests_this_run"],2)
    def test_retry_shorter_translation(self):
        self.data["segments"]=[{"id":1,"start":0,"end":1.3,"text":"Understand it."}]
        self.english.write_text(json.dumps(self.data),encoding="utf-8")
        service=FakeChat([
            choice([{"id":1,"text":"यहाँ पर हमें उस जरूरी विषय को बहुत अच्छी तरह और ध्यान से समझना चाहिए।"}]),
            choice([{"id":1,"text":"इसे समझिए।"}])])
        result=OpenAIHindiTranslator(client(service)).run(self.context)
        self.assertEqual(len(service.calls),2)
        self.assertIn("revision_request",json.loads(service.calls[-1]["messages"][1]["content"]))
        self.assertEqual(result["segments"],1)
    def test_batch_checkpoint_resumes_without_duplicate_bill(self):
        failing=FakeChat([choice([{"id":1,"text":"एक्टिव रिकॉल का अभ्यास करें।"}]),
                          RuntimeError("API timeout")])
        with self.assertRaisesRegex(RuntimeError,"API timeout"):
            OpenAIHindiTranslator(client(failing)).run(self.context)
        self.assertFalse((self.root/"translate"/"hindi.srt").exists())
        retry=FakeChat([choice([{"id":2,"text":"कल फिर पढ़िए।"}])])
        result=OpenAIHindiTranslator(client(retry)).run(self.context)
        self.assertEqual(result["batches_reused"],1)
        self.assertEqual(len(retry.calls),1)
    def test_missing_glossary_fails_without_partial_output(self):
        self.cfg["translation"]["max_quality_attempts"]=2
        service=FakeChat([choice([{"id":1,"text":"इसे सीखें।"}]),
                          choice([{"id":1,"text":"इसे सीखें।"}])])
        with self.assertRaisesRegex(ValueError,"Unable to fit"):
            OpenAIHindiTranslator(client(service)).run(self.context)
        self.assertFalse((self.root/"translate"/"hindi.json").exists())
    def test_existing_checkpoints_are_verified(self):
        first=FakeChat([choice([{"id":1,"text":"एक्टिव रिकॉल का अभ्यास करें।"}]),
                        choice([{"id":2,"text":"कल फिर पढ़िए।"}])])
        OpenAIHindiTranslator(client(first)).run(self.context)
        new=FakeChat([])
        result=OpenAIHindiTranslator(client(new)).run(self.context)
        self.assertEqual(result["batches_reused"],2)
        self.assertEqual(len(new.calls),0)
    def test_structured_json_schema_requested(self):
        service=FakeChat([choice([{"id":1,"text":"एक्टिव रिकॉल का अभ्यास करें।"}]),
                          choice([{"id":2,"text":"कल फिर पढ़िए।"}])])
        OpenAIHindiTranslator(client(service)).run(self.context)
        fmt=service.calls[0]["response_format"]
        self.assertEqual(fmt["type"],"json_schema")
        self.assertTrue(fmt["json_schema"]["strict"])
        self.assertEqual(service.calls[0]["model"],"gpt-4o-mini")


if __name__=="__main__":
    unittest.main()
