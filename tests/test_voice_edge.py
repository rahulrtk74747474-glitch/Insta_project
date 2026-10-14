"""Stage 6: independent Hindi neural voice provider tests, no live service."""
from __future__ import annotations
import json,math,sys,tempfile,types,unittest
from pathlib import Path
from unittest.mock import patch
from hindi_pipeline.voice_edge import EdgeHindiVoice
from hindi_pipeline.orchestrator import Pipeline
from hindi_pipeline.voice import _wav_length
from hindi_pipeline.common import command

class FakeCommunicate:
    calls=[]
    def __init__(self,text,voice,rate):
        self.text=text;self.voice=voice;self.rate=rate
        self.calls.append((text,voice,rate))
    async def save(self,path):
        command(["ffmpeg","-hide_banner","-loglevel","error","-y","-f","lavfi",
                 "-i","sine=frequency=330:sample_rate=24000","-t","1.4","-c:a",
                 "libmp3lame",path])

class TestHindiEdge(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.settings={"provider":"edge","model":"edge-neural",
                       "voice":"hi-IN-MadhurNeural","rate":"-2%",
                       "auto_shorten":False,"max_tempo":1.18}
    def test_provider_and_real_wav_conversion(self):
        tts=EdgeHindiVoice()
        tts.settings=self.settings
        with patch.dict(sys.modules,{"edge_tts":types.SimpleNamespace(Communicate=FakeCommunicate)}):
            out=self.root/"speech.wav"
            tts._synthesize("सोचो, आज पढ़ाई का समय है।",out,"edge-neural",
                             "hi-IN-MadhurNeural","")
        self.assertGreater(_wav_length(out),1.0)
        self.assertEqual(FakeCommunicate.calls[-1][1:],
                         ("hi-IN-MadhurNeural","-2%"))
    def test_unsupported_voice_and_rate_rejected(self):
        provider=EdgeHindiVoice();provider.settings=self.settings
        with self.assertRaisesRegex(ValueError,"Hindi"):
            provider._synthesize("test",self.root/"bad.wav","x","en-US-GuyNeural","")
        provider.settings={**self.settings,"rate":"faster; rm -rf /"}
        with self.assertRaisesRegex(ValueError,"rate"):
            provider._synthesize("test",self.root/"bad.wav","x","hi-IN-MadhurNeural","")
    def test_pipeline_provider_switch(self):
        cfg={"output_dir":str(self.root/"out"),"database":str(self.root/"state.sqlite"),
             "voice":self.settings}
        pipeline=Pipeline(cfg)
        self.assertEqual(type(pipeline.providers["voice"]).__name__,"EdgeHindiVoice")
        cfg["voice"]={**self.settings,"provider":"openai"}
        self.assertEqual(type(Pipeline(cfg).providers["voice"]).__name__,"OpenAIHindiVoice")
        cfg["voice"]={**self.settings,"provider":"nonsense"}
        with self.assertRaisesRegex(ValueError,"Unsupported voice provider"):
            Pipeline(cfg)
    def test_rate_change_invalidates_tts_cache(self):
        from hindi_pipeline.voice import _signature
        doc={"blocks":[{"id":1,"narration":"एक लाइन","start":0.2,"end":2.0}]}
        p=_signature(doc,self.settings,4.0)
        p2=_signature(doc,{**self.settings,"rate":"+2%"},4.0)
        self.assertNotEqual(p,p2)

if __name__=="__main__":
    unittest.main()
