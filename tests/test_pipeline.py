"""Offline unit tests: no API key, model download or platform account."""
import json, tempfile, unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock,patch

from hindi_pipeline.common import hms,write_srt
from hindi_pipeline.ingest import YtDlpOrFile
from hindi_pipeline.transcribe import FasterWhisper
from hindi_pipeline.translate import OpenAIHindiTranslator
from hindi_pipeline.orchestrator import Pipeline

class Fake:
    def __init__(self,name):self.name=name;self.called=0
    def run(self,context):
        self.called+=1
        p=Path(context["folder"])/(self.name+".json");p.write_text("{}")
        return {"artifact":str(p),"stage":self.name}

class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.source=self.root/"sample.mp4";self.source.write_bytes(b"x")
        self.providers={s:Fake(s) for s in ("ingest","transcribe","translate")}
        self.p=Pipeline({"output_dir":str(self.root/"out"),"database":str(self.root/"db.sqlite")},self.providers)
    def test_rights_required(self):
        with self.assertRaises(PermissionError):self.p.create(str(self.source),"local",False)
        self.assertEqual(self.p.db.list(),[])
    def test_resume(self):
        id=self.p.create(str(self.source),"local",True)
        self.p.process(id);self.p.process(id)
        self.assertEqual([x.called for x in self.providers.values()],[1,1,1])
        self.p.process(id,force_stage="transcribe")
        self.assertEqual([x.called for x in self.providers.values()],[1,2,2])
        self.assertEqual(self.p.db.stage(id,"translate")["attempts"],2)
    def test_retry_failed_stage(self):
        class Flaky(Fake):
            def run(self,ctx):
                if not self.called:
                    self.called+=1;raise RuntimeError("temporary")
                return super().run(ctx)
        self.providers["transcribe"]=Flaky("transcribe")
        id=self.p.create(str(self.source),"local",True)
        with self.assertRaises(RuntimeError):self.p.process(id)
        self.assertEqual(self.p.db.stage(id,"transcribe")["status"],"failed")
        self.p.process(id)
        self.assertEqual(self.p.db.stage(id,"transcribe")["status"],"completed")
        self.assertEqual(self.providers["ingest"].called,1)
    def test_timestamps(self):
        self.assertEqual(hms(3601.001),"01:00:01,001")
        p=self.root/"s.srt"
        write_srt([{"start":0,"end":1.23,"text":"Hello"}],p)
        self.assertIn("00:00:00,000 --> 00:00:01,230",p.read_text())

class ProviderTests(unittest.TestCase):
    def test_ingest_local_and_mock_stems(self):
        with tempfile.TemporaryDirectory() as t:
            folder=Path(t);source=folder/"source.mp4";source.write_bytes(b"video")
            def fake_call(cmd,timeout=7200):
                if cmd[0]=="ffmpeg":Path(cmd[-1]).write_bytes(b"wave")
                if "demucs" in cmd:
                    out=folder/"ingest"/"stems"/"htdemucs"/"audio"
                    out.mkdir(parents=True)
                    (out/"vocals.wav").write_bytes(b"v")
                    (out/"no_vocals.wav").write_bytes(b"b")
                return ""
            with patch("hindi_pipeline.ingest.command",side_effect=fake_call), patch(
                "hindi_pipeline.ingest.probe",return_value={
                    "format":{"duration":"2.0"},"streams":[{"codec_type":"video"},{"codec_type":"audio"}]
                }):
                result=YtDlpOrFile().run({"folder":t,"source":str(source),
                    "source_type":"local","config":{"demucs":{"enabled":True}}})
            self.assertTrue(Path(result["vocals"]).exists())
            self.assertTrue(Path(result["no_vocals"]).exists())
            self.assertEqual(result["duration"],2.0)
    def test_whisper_words(self):
        import sys
        with tempfile.TemporaryDirectory() as t:
            seg=SimpleNamespace(start=0.1,end=2.1,text="Hello world",words=[
                SimpleNamespace(start=0.1,end=.8,word="Hello"),SimpleNamespace(start=1,end=2.1,word="world")])
            model=MagicMock();model.transcribe.return_value=([seg],SimpleNamespace(language="en"))
            with patch.dict(sys.modules,{"faster_whisper":SimpleNamespace(WhisperModel=lambda *a,**k:model)}):
                result=FasterWhisper().run({"folder":t,"config":{"whisper":{}},"previous":{"ingest":{"vocals":"/fake.wav"}}})
            data=json.loads(Path(result["english_json"]).read_text())
            self.assertEqual(data["segments"][0]["words"][1]["word"],"world")
            self.assertIn("Hello world",Path(result["english_srt"]).read_text())
    def test_hindi_translation(self):
        with tempfile.TemporaryDirectory() as t:
            j=Path(t)/"en.json";j.write_text(json.dumps({"segments":[{"id":1,"start":0,"end":2,
                                                                        "text":"Hello world"}]}))
            sdk=MagicMock()
            sdk.chat.completions.create.return_value=SimpleNamespace(choices=[SimpleNamespace(
                message=SimpleNamespace(content='{"items":[{"id":1,"text":"नमस्ते दुनिया"}]}'))])
            context={"folder":t,"config":{"translation":{"model":"gpt-4o-mini",
                        "glossary":{"world":"दुनिया"}}},"previous":{"transcribe":{"english_json":str(j)}}}
            result=OpenAIHindiTranslator(sdk).run(context)
            self.assertIn("नमस्ते दुनिया",Path(result["hindi_srt"]).read_text())
            self.assertEqual(sdk.chat.completions.create.call_args.kwargs["response_format"]["type"],"json_schema")
    def test_hindi_rejects_wrong_ids(self):
        with tempfile.TemporaryDirectory() as t:
            j=Path(t)/"en.json";j.write_text(json.dumps({"segments":[{"id":1,"start":0,"end":2,"text":"Hi"}]}))
            sdk=MagicMock();sdk.chat.completions.create.return_value=SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content='{"items":[{"id":3,"text":"नमस्ते"}]}'))])
            with self.assertRaisesRegex(ValueError,"missing, duplicate"):
                OpenAIHindiTranslator(sdk).run({"folder":t,"config":{"translation":{"model":"test"}},
                                                "previous":{"transcribe":{"english_json":str(j)}}})
if __name__=="__main__":unittest.main()
