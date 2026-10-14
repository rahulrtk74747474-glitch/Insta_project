"""Unit/integration tests for *local* OmniVoice provider; no private files or model weights."""
from __future__ import annotations

from array import array
import json
import math
from pathlib import Path
import sys
import tempfile
import types
import unittest
import wave
from unittest.mock import patch

from hindi_pipeline.orchestrator import Pipeline
from hindi_pipeline.voice_omnivoice import OmniVoiceHindiVoice, reference_files, reference_digest


RATE = 24000


def make_wav(p: Path, seconds=8.5, hz=180):
    pcm=array("h",(round(1500*math.sin(2*math.pi*hz*i/RATE))
                   for i in range(int(seconds*RATE))))
    with wave.open(str(p),"wb") as w:
        w.setnchannels(1);w.setsampwidth(2);w.setframerate(RATE)
        w.writeframes(pcm.tobytes())


def fake_sf_write(path,data,rate,subtype):
    assert rate == RATE and subtype == "PCM_16"
    pcm=array("h",(round(max(-1.,min(1.,v))*32767) for v in data))
    with wave.open(str(path),"wb") as w:
        w.setnchannels(1);w.setsampwidth(2);w.setframerate(rate)
        w.writeframes(pcm.tobytes())


class Model:
    def __init__(self):
        self.prompts=[]
        self.requests=[]
    def create_voice_clone_prompt(self, **kwargs):
        self.prompts.append(kwargs)
        return {"reference":kwargs["ref_audio"],"text":kwargs["ref_text"]}
    def generate(self,**kwargs):
        self.requests.append(kwargs)
        return [[math.sin(2*math.pi*240*i/RATE)*.15 for i in range(RATE)]]


class TestOmniVoice(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root=Path(temp.name)
        self.root=root
        ref=root/"private_hindi_voice.wav"
        transcript=root/"private_voice_transcript.txt"
        make_wav(ref)
        transcript.write_text("सोचो, तुम एग्जाम देने बैठे हो। पेपर सामने है।",encoding="utf-8")
        translated=root/"translate.json"
        translated.write_text(json.dumps({
            "mode":"spoken_adaptation","fingerprint":"test-user-voice",
            "blocks":[
                {"id":1,"start":0.3,"end":2.5,
                 "narration":"सोचो, एग्जाम सामने है।", "source_cue_ids":[1],
                 "source_english":"Imagine an exam."},
                {"id":2,"start":2.7,"end":5.4,
                 "narration":"सारा कुछ याद आ रहा है।","source_cue_ids":[2],
                 "source_english":"You remember everything."}
            ]},ensure_ascii=False),encoding="utf-8")
        self.settings={
            "provider":"omnivoice","model":"k2-fsa/OmniVoice",
            "voice":"personal_hindi_reference",
            "reference_voice_consent_confirmed":True,
            "reference_audio":str(ref),
            "reference_text_file":str(transcript),
            "device":"auto","num_step":16,"generation_speed":1,
            "max_tempo":1.18,"auto_shorten":False,
        }
        self.context={
            "folder":str(root),
            "config":{"voice":self.settings},
            "previous":{
                "ingest":{"duration":6.0},
                "translate":{"hindi_voice_script_json":str(translated)},
            }
        }

    def test_clone_prompt_reused_for_all_ideas_without_openai(self):
        fake=Model()
        provider=OmniVoiceHindiVoice(model_instance=fake)
        with patch.dict(sys.modules,{"soundfile":types.SimpleNamespace(write=fake_sf_write)}):
            result=provider.run(self.context)
            self.assertEqual(result["provider"],"omnivoice")
            self.assertEqual(result["synthesis_calls"],2)
            self.assertEqual(result["api_requests"],0)
            self.assertEqual(len(fake.prompts),1)
            self.assertEqual(len(fake.requests),2)
            self.assertEqual(fake.requests[0]["voice_clone_prompt"]["text"],
                             "सोचो, तुम एग्जाम देने बैठे हो। पेपर सामने है।")
            self.assertEqual(fake.requests[1]["num_step"],16)
            with wave.open(str(result["hindi_voice_wav"]),"rb") as reader:
                self.assertEqual(reader.getnframes(),RATE*6)
            report=json.loads(Path(result["voice_report"]).read_text())
            self.assertEqual(report["provider"],"omnivoice")
            self.assertEqual(report["synthesis_calls_this_run"],2)

    def test_cached_voice_rerun_no_model_or_soundfile_required(self):
        with patch.dict(sys.modules,{"soundfile":types.SimpleNamespace(write=fake_sf_write)}):
            OmniVoiceHindiVoice(model_instance=Model()).run(self.context)
        provider=OmniVoiceHindiVoice()
        result=provider.run(self.context)
        self.assertEqual(result["synthesis_calls"],0)
        self.assertEqual(result["cached_blocks"],2)

    def test_changed_reference_invalidates_old_cache(self):
        a=OmniVoiceHindiVoice.fingerprint(self.context)
        transcript=Path(self.settings["reference_text_file"])
        transcript.write_text("सोचो, तुम एग्जाम देने बैठे हो। अब ज़रा ध्यान दो।",encoding="utf-8")
        b=OmniVoiceHindiVoice.fingerprint(self.context)
        self.assertNotEqual(a,b)
        with open(self.settings["reference_audio"],"ab") as f: f.write(b"\x00")
        # Raw bytes changing also invalidate signature; raw WAV remains parsable.
        c=OmniVoiceHindiVoice.fingerprint(self.context)
        self.assertNotEqual(b,c)

    def test_reference_requires_permission_and_matching_hindi_text(self):
        with self.assertRaises(PermissionError):
            reference_files({**self.settings,"reference_voice_consent_confirmed":False})
        with self.assertRaises(FileNotFoundError):
            reference_files({**self.settings,"reference_audio":"/missing/voice.wav"})
        Path(self.settings["reference_text_file"]).write_text("bad",encoding="utf-8")
        with self.assertRaises(ValueError):
            reference_files(self.settings)

    def test_ref_length_guard(self):
        path=Path(self.settings["reference_audio"])
        make_wav(path,11.0)
        with self.assertRaisesRegex(ValueError,"3–10"):
            reference_files(self.settings)

    def test_provider_selector_is_explicit(self):
        cfg={"output_dir":str(self.root/"out"),"database":str(self.root/"db.sqlite"),
             "voice":self.settings}
        pipe=Pipeline(cfg)
        self.assertEqual(type(pipe.providers["voice"]).__name__,"OmniVoiceHindiVoice")
        cfg["voice"]={"provider":"openai"}
        self.assertEqual(type(Pipeline(cfg).providers["voice"]).__name__,"OpenAIHindiVoice")
        cfg["voice"]={"provider":"espeak"}
        with self.assertRaisesRegex(ValueError,"Unsupported voice.provider"):
            Pipeline(cfg)

    def test_omni_sdk_loader_uses_official_factory(self):
        fake=Model()
        observed=[]
        class Loader:
            @staticmethod
            def from_pretrained(model_id,device_map,dtype):
                observed.append((model_id,device_map,dtype))
                return fake
        mocktorch=types.SimpleNamespace(
            cuda=types.SimpleNamespace(is_available=lambda:False),
            backends=types.SimpleNamespace(mps=types.SimpleNamespace(is_available=lambda:False)),
            float16="fp16",float32="fp32",
        )
        with patch.dict(sys.modules,{"omnivoice":types.SimpleNamespace(OmniVoice=Loader),
                                     "torch":mocktorch,
                                     "soundfile":types.SimpleNamespace(write=fake_sf_write)}):
            provider=OmniVoiceHindiVoice()
            result=provider.run(self.context)
        self.assertEqual(observed,[("k2-fsa/OmniVoice","cpu","fp32")])
        self.assertEqual(result["provider"],"omnivoice")
        self.assertEqual(len(fake.prompts),1)


if __name__=="__main__":
    unittest.main()
