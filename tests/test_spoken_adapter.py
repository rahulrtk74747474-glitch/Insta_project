"""Stage 3 natural Hindi tests: no key or external LLM needed."""
from __future__ import annotations
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from hindi_pipeline.orchestrator import Pipeline
from hindi_pipeline.translate_spoken import (
    NaturalHindiScriptAdapter, idea_blocks, _subtitles, _fingerprint,
)
from hindi_pipeline.translation_quality import check_english_segments


def sample_english():
    return {"segments": [
        {"id":1,"start":0.0,"end":3.0,"text":"Imagine you sit for an exam."},
        {"id":2,"start":3.1,"end":8.5,"text":"And everything just clicks in your mind."},
        {"id":3,"start":8.8,"end":12.0,"text":"Now learn the time loop trick."},
        {"id":4,"start":12.1,"end":17.1,"text":"Practice it instead of rereading all day."},
    ]}


def reply(items):
    return SimpleNamespace(choices=[SimpleNamespace(
        finish_reason="stop", message=SimpleNamespace(
            content=json.dumps({"items":items},ensure_ascii=False),refusal=None))])


class Fake:
    def __init__(self,responses):
        self.responses=list(responses)
        self.calls=[]
    def create(self,**kwargs):
        self.calls.append(kwargs)
        if not self.responses:
            raise RuntimeError("Unexpected API call")
        response=self.responses.pop(0)
        if isinstance(response,Exception):
            raise response
        return response


def client(fake):
    return SimpleNamespace(chat=SimpleNamespace(completions=fake))


class GroupingTests(unittest.TestCase):
    def test_group_whole_ideas_not_individual_cues(self):
        cues=check_english_segments(sample_english())
        grouped=idea_blocks(cues,min_seconds=6,max_seconds=14,max_cues=4)
        self.assertEqual(len(grouped),2)
        self.assertEqual(grouped[0]["source_cue_ids"],[1,2])
        self.assertEqual(grouped[1]["source_cue_ids"],[3,4])
        self.assertEqual([x for g in grouped for x in g["source_cue_ids"]],[1,2,3,4])
        self.assertEqual(grouped[0]["start"],0)
        self.assertEqual(grouped[1]["end"],17.1)

    def test_split_caption_from_spoken_words_not_english_cues(self):
        blocks=[{"id":1,"start":0,"end":9,
            "narration":"सोचो, एग्जाम देने बैठे हो और जो भी पढ़ा था, सब तुम्हें फटाफट याद आ रहा है।"}]
        cues=_subtitles(blocks,max_chars=45)
        self.assertGreater(len(cues),1)
        self.assertTrue(all(len(line)<=42 for c in cues for line in c["display_lines"]))
        self.assertEqual(cues[0]["start"],0)
        self.assertEqual(cues[-1]["end"],9)
        self.assertTrue(all(c["alignment_status"]=="estimated_until_hindi_tts" for c in cues))

    def test_fingerprint_changed_when_style_changes(self):
        original=sample_english()
        config={"model":"gpt-4o-mini","audience":"tum","batch_size":4,"mode":"spoken_adaptation"}
        v1=_fingerprint(original,config)
        self.assertNotEqual(v1,_fingerprint(original,{**config,"max_group_seconds":9}))
        self.assertNotEqual(v1,_fingerprint(original,{**config,"audience":"aap"}))

    def test_provider_switching(self):
        with tempfile.TemporaryDirectory() as temp:
            config={"output_dir":str(Path(temp)/"out"),"database":str(Path(temp)/"db.sqlite3")}
            default=Pipeline(config)
            self.assertIsInstance(default.providers["translate"],NaturalHindiScriptAdapter)
            old=Pipeline({**config,"translation":{"mode":"subtitle_literal"}})
            self.assertEqual(old.providers["translate"].__class__.__name__,"OpenAIHindiTranslator")
            with self.assertRaisesRegex(ValueError,"Unknown translation.mode"):
                Pipeline({**config,"translation":{"mode":"invalid"}})


class SpokenProviderTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.folder=Path(self.temp.name)
        self.input=self.folder/"english.json"
        self.input.write_text(json.dumps(sample_english()),encoding="utf-8")
        self.settings={"provider":"openai","mode":"spoken_adaptation",
            "model":"gpt-4o-mini","batch_size":2,"max_quality_attempts":2,
            "min_group_seconds":6,"max_group_seconds":14,"max_group_cues":4,
            "speed_tolerance":1.15,"audience":"tum",
            "glossary":{"time loop":"टाइम लूप"}}
        self.ctx={"config":{"translation":self.settings},"folder":str(self.folder),
            "previous":{"transcribe":{"english_json":str(self.input)}}}

    def answers(self):
        return [{"id":1,"text":"सोचो, एग्जाम में बैठे हो और सब कुछ फटाफट याद आ रहा है।"},
                {"id":2,"text":"अब टाइम लूप वाली ट्रिक समझो। बार-बार रटने की जगह खुद प्रैक्टिस करो।"}]

    def test_real_script_files_and_derived_hindi_subtitles(self):
        api=Fake([reply(self.answers())])
        r=NaturalHindiScriptAdapter(client(api)).run(self.ctx)
        self.assertEqual(r["spoken_blocks"],2)
        self.assertEqual(r["provider"],"openai-spoken-adaptation")
        self.assertTrue(Path(r["hindi_srt"]).exists())
        self.assertTrue(Path(r["hindi_voice_script_json"]).exists())
        txt=Path(r["hindi_voice_script_txt"]).read_text()
        self.assertIn("सोचो, एग्जाम",txt)
        self.assertIn("टाइम लूप",txt)
        self.assertNotIn("Imagine",txt)
        v=json.loads(Path(r["hindi_voice_script_json"]).read_text())
        self.assertEqual(v["blocks"][0]["source_cue_ids"],[1,2])
        self.assertEqual(v["blocks"][1]["source_cue_ids"],[3,4])
        subtitle=json.loads(Path(r["hindi_json"]).read_text())
        self.assertEqual(subtitle["alignment"],"estimated_not_tts_aligned")
        self.assertEqual(subtitle["segments"][0]["source_block_id"],1)
        report=json.loads(Path(r["translation_report"]).read_text())
        self.assertEqual(report["source_cues"],4)
        self.assertEqual(report["spoken_idea_blocks"],2)
        self.assertTrue(report["source_cues_preserved_in_mapping"])
        self.assertIn("untrusted",api.calls[0]["messages"][0]["content"].lower())

    def test_retries_too_long_paragraph(self):
        self.settings["batch_size"]=2
        bad=[{"id":1,"text":"अगर तुम बड़ी परीक्षा देने बैठ रहे हो तो ज़रा सोचकर देखो कि तुमने इस खास समय तक हर चीज़ का अभ्यास इतनी बार कर लिया है कि कोई भी चीज़ भूलना लगभग नामुमकिन हो गया है क्योंकि यह अनुभव तुम्हारे दिमाग में पूरी तरह बैठ चुका है।"},
             self.answers()[1]]
        api=Fake([reply(bad),reply(self.answers())])
        out=NaturalHindiScriptAdapter(client(api)).run(self.ctx)
        self.assertEqual(len(api.calls),2)
        second=json.loads(api.calls[1]["messages"][1]["content"])
        self.assertIn("please_revise",second)
        self.assertEqual(out["spoken_blocks"],2)

    def test_batch_resume_after_failure(self):
        self.settings["batch_size"]=1
        first=Fake([reply([self.answers()[0]]),RuntimeError("Temporary API error")])
        with self.assertRaisesRegex(RuntimeError,"Temporary API error"):
            NaturalHindiScriptAdapter(client(first)).run(self.ctx)
        self.assertFalse((self.folder/"translate"/"hindi_voice_script.txt").exists())
        retry=Fake([reply([self.answers()[1]])])
        result=NaturalHindiScriptAdapter(client(retry)).run(self.ctx)
        self.assertEqual(result["batches_reused"],1)
        self.assertEqual(len(retry.calls),1)

    def test_glossary_missing_must_fail_not_fake_success(self):
        self.settings["max_quality_attempts"]=2
        bad=[self.answers()[0],{"id":2,"text":"बस एक अच्छी ट्रिक अपनाओ, फिर खुद प्रैक्टिस करो।"}]
        api=Fake([reply(bad),reply(bad)])
        with self.assertRaisesRegex(ValueError,"Unable to produce valid spoken Hindi"):
            NaturalHindiScriptAdapter(client(api)).run(self.ctx)
        self.assertFalse((self.folder/"translate"/"hindi_voice_script.txt").exists())

    def test_cached_narration_is_reused(self):
        api=Fake([reply(self.answers())])
        NaturalHindiScriptAdapter(client(api)).run(self.ctx)
        replay=Fake([])
        r=NaturalHindiScriptAdapter(client(replay)).run(self.ctx)
        self.assertEqual(len(replay.calls),0)
        self.assertEqual(r["batches_reused"],1)
        self.assertEqual(r["spoken_blocks"],2)


if __name__=="__main__":
    unittest.main()
