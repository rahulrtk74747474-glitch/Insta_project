"""Stage 4: synthetic WAV and mocked TTS (no paid API/key). Requires local FFmpeg."""
from __future__ import annotations

import json
import math
from pathlib import Path
import sqlite3
import tempfile
import unittest
import wave
from array import array
from unittest.mock import patch

from hindi_pipeline.db import JobDB
from hindi_pipeline.orchestrator import Pipeline
from hindi_pipeline.translate_spoken import spoken_style_problems
from hindi_pipeline.voice import (
    OpenAIHindiVoice, _pcm_audio, _srt_from_audio, _signature,
)

RATE=24000


def synthetic_wav(dest: Path, seconds:float):
    frames=max(1,round(seconds*RATE))
    samples=array("h",(int(1500*math.sin(2*math.pi*440*i/RATE)) for i in range(frames)))
    with wave.open(str(dest),"wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(samples.tobytes())


class FakeHindiVoice(OpenAIHindiVoice):
    def __init__(self,durations):
        super().__init__(client=None)
        self.durations=list(durations)
        self.synth_calls=0
    def _synthesize(self,text,output,model,voice,instructions):
        if not self.durations:
            raise AssertionError("Synthesis was unexpectedly retried")
        synthetic_wav(output,self.durations.pop(0))
        self.synth_calls+=1


class TestStage4(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.stage3=self.root/"translate"
        self.stage3.mkdir()
        self.script=self.stage3/"hindi_voice_script.json"
        self.subtitles=self.stage3/"hindi.json"
        self.blocks=[
            {"id":1,"start":.25,"end":2.75,"narration":"सोचो, एग्जाम में सब याद आ रहा है।",
             "source_cue_ids":[1,2]},
            {"id":2,"start":3.5,"end":6.5,"narration":"अब टाइम लूप वाली ट्रिक समझो।",
             "source_cue_ids":[3]}
        ]
        self.script.write_text(json.dumps({
            "mode":"spoken_adaptation","language":"hi","fingerprint":"test-caption",
            "blocks":self.blocks},ensure_ascii=False),encoding="utf-8")
        self.subtitles.write_text(json.dumps({"segments":[
            {"source_block_id":1,"text":"सोचो, एग्जाम में सब याद आ रहा है।"},
            {"source_block_id":2,"text":"अब टाइम लूप वाली ट्रिक समझो।"}]},
            ensure_ascii=False),encoding="utf-8")
        self.ctx={
            "folder":str(self.root),
            "config":{"voice":{"provider":"openai","model":"gpt-4o-mini-tts",
                                "voice":"marin","max_tempo":1.18}},
            "previous":{"translate":{"hindi_voice_script_json":str(self.script),
                                     "hindi_json":str(self.subtitles)},
                        "ingest":{"duration":7.2}}
        }

    def test_real_synthetic_audio_timeline_and_no_overlap(self):
        voice=FakeHindiVoice([1.1,2.4])
        out=voice.run(self.ctx)
        self.assertEqual(voice.synth_calls,2)
        wav=Path(out["hindi_voice_wav"])
        self.assertTrue(wav.is_file())
        with wave.open(str(wav),"rb") as source:
            self.assertEqual(source.getframerate(),RATE)
            self.assertEqual(source.getnchannels(),1)
            self.assertEqual(source.getnframes(),round(7.2*RATE))
        sample=_pcm_audio(wav)
        self.assertTrue(all(x==0 for x in sample[:round(.2*RATE)]))
        self.assertTrue(any(x for x in sample[round(.25*RATE):round(1*RATE)]))
        self.assertTrue(all(x==0 for x in sample[round(2*RATE):round(3*RATE)]))
        self.assertTrue(any(x for x in sample[round(3.5*RATE):round(4.2*RATE)]))
        report=json.loads(Path(out["voice_report"]).read_text(encoding="utf-8"))
        self.assertEqual(report["spoken_blocks"],2)
        self.assertEqual(report["api_requests_this_run"],2)
        self.assertEqual(report["cached_blocks_this_run"],0)
        self.assertEqual(report["sample_rate_hz"],RATE)
        self.assertEqual(len(report["blocks"]),2)
        estimated=json.loads(Path(out["hindi_tts_estimated_json"]).read_text(encoding="utf-8"))
        self.assertEqual(estimated["alignment"],"estimated_inside_measured_block_not_word_aligned")
        self.assertIn("00:00:00",Path(out["hindi_tts_estimated_srt"]).read_text())

    def test_cached_audio_survives_new_run_without_api(self):
        FakeHindiVoice([1,2]).run(self.ctx)
        empty=FakeHindiVoice([])
        result=empty.run(self.ctx)
        self.assertEqual(empty.synth_calls,0)
        self.assertEqual(result["cached_blocks"],2)
        self.assertEqual(result["api_requests"],0)

    def test_long_speech_fails_without_clipping(self):
        voice=FakeHindiVoice([4])
        with self.assertRaisesRegex(ValueError,"rewrite this idea more concisely"):
            voice.run(self.ctx)
        self.assertEqual(voice.synth_calls,1)
        self.assertFalse((self.root/"voice"/"hindi_voice.wav").exists())
        with self.assertRaisesRegex(ValueError,"rewrite this idea more concisely"):
            FakeHindiVoice([]).run(self.ctx) # cached excessively long raw WAV

    def test_auto_tempo_within_safe_cap(self):
        voice=FakeHindiVoice([2.65,2.6])  # first slot is only 2.5s
        out=voice.run(self.ctx)
        report=json.loads(Path(out["voice_report"]).read_text(encoding="utf-8"))
        self.assertGreater(report["blocks"][0]["tempo_factor"],1)
        self.assertLessEqual(report["blocks"][0]["fitted_duration_s"],2.55)

    def test_stage3_literal_input_rejected(self):
        self.ctx["previous"]["translate"].pop("hindi_voice_script_json")
        with self.assertRaisesRegex(ValueError,"spoken_adaptation"):
            FakeHindiVoice([]).run(self.ctx)

    def test_fingerprint_changes_on_voice_or_script(self):
        src=json.loads(self.script.read_text())
        self.assertNotEqual(
            _signature(src,{"model":"gpt-4o-mini-tts","voice":"marin"},7.2),
            _signature(src,{"model":"gpt-4o-mini-tts","voice":"coral"},7.2))
        modified=json.loads(self.script.read_text())
        modified["blocks"][0]["narration"]="दिमाग में सब क्लियर है।"
        self.assertNotEqual(
            _signature(src,{"voice":"marin"},7.2),
            _signature(modified,{"voice":"marin"},7.2))

    def test_stage3_rejects_stiff_wording(self):
        self.assertEqual(spoken_style_problems([{"id":1,"text":"सोचो, एग्जाम में सब याद है।"}]),[])
        errors=spoken_style_problems([{"id":2,"text":"कल्पना कीजिए कि मस्तिष्क काम कर रहा है।"}])
        self.assertGreaterEqual(len(errors),2)

    def test_sqlite_migrates_existing_stage1_stage2_stage3_jobs(self):
        legacy=self.root/"legacy.sqlite"
        conn=sqlite3.connect(legacy)
        conn.executescript("""
        CREATE TABLE jobs (
            id TEXT PRIMARY KEY, source TEXT NOT NULL, source_type TEXT NOT NULL,
            rights_confirmed INTEGER NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE TABLE stage_runs (
            job_id TEXT NOT NULL, stage TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending', attempts INTEGER NOT NULL DEFAULT 0,
            result_json TEXT, error TEXT, started_at TEXT, finished_at TEXT,
            PRIMARY KEY(job_id,stage)
        );
        INSERT INTO jobs VALUES ('abc','/tmp/example.mp4','local',1,'old','old');
        INSERT INTO stage_runs(job_id,stage,status) VALUES('abc','ingest','completed');
        INSERT INTO stage_runs(job_id,stage,status) VALUES('abc','transcribe','completed');
        INSERT INTO stage_runs(job_id,stage,status) VALUES('abc','translate','completed');
        """)
        conn.commit();conn.close()
        db=JobDB(legacy)
        self.assertEqual(db.stage("abc","voice")["status"],"pending")
        self.assertEqual(db.stage("abc","translate")["status"],"completed")

    def test_pipeline_has_voice_as_stage_four(self):
        with tempfile.TemporaryDirectory() as td:
            config={"output_dir":str(Path(td)/"out"),"database":str(Path(td)/"db.sqlite")}
            pipeline=Pipeline(config)
            self.assertIn("voice",pipeline.providers)
            self.assertEqual(pipeline.providers["voice"].__class__.__name__,"OpenAIHindiVoice")


if __name__=="__main__":
    unittest.main()
