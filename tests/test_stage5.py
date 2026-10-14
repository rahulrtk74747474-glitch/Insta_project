"""Stage 5 offline integration tests: real FFmpeg, libass and synthetic English/Hindi audio."""
from __future__ import annotations
import json
import math
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from hindi_pipeline.common import STAGES,command,probe
from hindi_pipeline.orchestrator import Pipeline
from hindi_pipeline.render import HindiVideoComposer, _dimensions, _video_filter


def run(*args):
    command(list(args),timeout=120)

def goertzel(samples,rate,frequency):
    """Single-frequency energy to show English source audio was not retained."""
    w=2*math.pi*frequency/rate
    coeff=2*math.cos(w)
    prev=prevprev=0
    for v in samples:
        new=v+coeff*prev-prevprev
        prevprev,prev=prev,new
    return max(0,prevprev*prevprev+prev*prev-coeff*prev*prevprev)


class RenderTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix="hindi stage5 test ")
        self.addCleanup(self.tmp.cleanup)
        self.base=Path(self.tmp.name)
        self.video=self.base/"source file.mp4"
        self.voice=self.base/"hindi_voice.wav"
        self.srt=self.base/"hindi subtitles.srt"
        self.context={
            "folder":str(self.base),
            "config":{"render":{
                "landscape":[320,180],"portrait":[180,320],
                "portrait_mode":"fit","fps":15,"preset":"ultrafast",
                "crf":32,"burn_subtitles":True,
                "subtitle_font":"Noto Sans Devanagari","subtitle_font_size":13,
                "mix_separated_background":False}},
            "previous":{"ingest":{"video":str(self.video),"duration":3.2,"no_vocals":None},
                        "voice":{"hindi_voice_wav":str(self.voice),
                                 "hindi_tts_estimated_srt":str(self.srt),
                                 "fingerprint":"voice-fixture-123"}}}
        run("ffmpeg","-hide_banner","-loglevel","error","-y",
            "-f","lavfi","-i","testsrc2=size=320x180:rate=15",
            "-f","lavfi","-i","sine=frequency=220:sample_rate=24000",
            "-t","3.2","-c:v","libx264","-preset","ultrafast",
            "-pix_fmt","yuv420p","-c:a","aac",str(self.video))
        run("ffmpeg","-hide_banner","-loglevel","error","-y",
            "-f","lavfi","-i","sine=frequency=440:sample_rate=24000",
            "-t","3.2","-ac","1","-ar","24000","-c:a","pcm_s16le",str(self.voice))
        self.srt.write_text("1\n00:00:00,200 --> 00:00:02,500\n"
                            "सोचो, एग्जाम देने बैठे हो।\n\n"
                            "2\n00:00:02,600 --> 00:00:03,100\n"
                            "सब कुछ याद आ रहा है।\n",encoding="utf-8")

    def test_both_aspect_ratios_hindi_audio_and_subtitles(self):
        output=HindiVideoComposer().run(self.context)
        self.assertTrue(Path(output["hindi_portrait_mp4"]).is_file())
        self.assertTrue(Path(output["hindi_landscape_mp4"]).is_file())
        self.assertTrue(Path(output["render_report"]).is_file())
        report=json.loads(Path(output["render_report"]).read_text())
        self.assertFalse(report["original_english_audio_included"])
        self.assertFalse(report["background_from_demucs_only"])
        self.assertTrue(report["burned_in_hindi_subtitles"])
        self.assertEqual(report["subtitle_alignment"],"estimated_inside_measured_block_not_word_aligned")
        for variant, dimensions in (("landscape",(320,180)),("portrait",(180,320))):
            item=report["outputs"][variant]
            self.assertEqual((item["width"],item["height"]),dimensions)
            self.assertAlmostEqual(item["duration_seconds"],3.2,delta=.25)
            self.assertEqual(item["audio_codec"],"aac")
            self.assertEqual(item["video_codec"],"h264")

        if os.environ.get("STAGE5_SAVE_SAMPLE") == "1":
            # Public CI artifacts contain only our synthetic color-test video/tone,
            # NOT the user's copyrighted/private original clip or live Hindi voice.
            preview=Path("dist")/"stage5_synthetic_preview"
            preview.mkdir(parents=True,exist_ok=True)
            shutil.copy2(output["hindi_landscape_mp4"],preview/"synthetic_landscape.mp4")
            shutil.copy2(output["hindi_portrait_mp4"],preview/"synthetic_portrait.mp4")
            shutil.copy2(output["render_report"],preview/"render_report.json")
            (preview/"README.txt").write_text(
                "SYNTHETIC test only. Video = FFmpeg test colors; English stand-in = 220 Hz tone; "
                "Hindi stand-in = 440 Hz tone. These are NOT real voices or the user video. "
                "Both mp4s intentionally contain only the Hindi stand-in audio. "
                "Subtitle text is a test fixture, and timing is estimated.\n",encoding="utf-8")

        audio_out=self.base/"extracted_from_render.wav"
        run("ffmpeg","-hide_banner","-loglevel","error","-y",
            "-i",output["hindi_landscape_mp4"],"-vn","-ac","1",
            "-ar","24000","-c:a","pcm_s16le",str(audio_out))
        import wave
        from array import array
        with wave.open(str(audio_out),"rb") as wav:
            samples=array("h")
            samples.frombytes(wav.readframes(24000))
        energy_440=goertzel(samples,24000,440)
        energy_220=goertzel(samples,24000,220)
        self.assertGreater(energy_440,energy_220*20,"Original English source tone leaked into Hindi soundtrack")

    def test_background_requires_genuine_separated_stem(self):
        self.context["config"]["render"]["mix_separated_background"]=True
        with self.assertRaisesRegex(ValueError,"isolated no_vocals"):
            HindiVideoComposer().run(self.context)

    def test_missing_srt_rejected_when_burn_requested(self):
        self.srt.unlink()
        with self.assertRaisesRegex(ValueError,"Stage 4 estimated Hindi SRT"):
            HindiVideoComposer().run(self.context)

    def test_invalid_duration_fails(self):
        other=self.base/"short_voice.wav"
        run("ffmpeg","-hide_banner","-loglevel","error","-y",
            "-f","lavfi","-i","sine=frequency=440:sample_rate=24000",
            "-t","0.8","-c:a","pcm_s16le",str(other))
        self.context["previous"]["voice"]["hindi_voice_wav"]=str(other)
        with self.assertRaisesRegex(ValueError,"aligned to the source"):
            HindiVideoComposer().run(self.context)

    def test_render_without_burn_for_headless_cases(self):
        settings=self.context["config"]["render"]
        settings["burn_subtitles"]=False
        settings["portrait_mode"]="fill"
        self.srt.unlink()
        result=HindiVideoComposer().run(self.context)
        self.assertTrue(Path(result["hindi_portrait_mp4"]).stat().st_size>1024)
        report=json.loads(Path(result["render_report"]).read_text())
        self.assertFalse(report["burned_in_hindi_subtitles"])
        self.assertEqual(report["portrait_mode"],"fill")

    def test_config_fingerprint_changes(self):
        a=HindiVideoComposer.fingerprint(self.context)
        self.context["config"]["render"]["portrait_mode"]="fill"
        b=HindiVideoComposer.fingerprint(self.context)
        self.assertNotEqual(a,b)

    def test_reject_dimensions_and_dangerous_font(self):
        for dimensions in ([301,181],[12,16],["bad",100]):
            with self.assertRaises((ValueError,TypeError)):
                _dimensions(dimensions)
        with self.assertRaisesRegex(ValueError,"Unsafe font"):
            _video_filter(320,180,"fit",Path("/tmp/sub.srt"),"Arial:bad",13,20)

    def test_pipeline_has_render_and_migrates_old_jobs(self):
        cfg={"output_dir":str(self.base/"jobs"),"database":str(self.base/"state.db")}
        pipeline=Pipeline(cfg)
        self.assertEqual(STAGES[-1],"render")
        self.assertEqual(pipeline.providers["render"].__class__.__name__,"HindiVideoComposer")
        job=pipeline.create(str(self.video),"local",True)
        self.assertEqual(pipeline.db.stage(job,"render")["status"],"pending")


if __name__=="__main__":
    unittest.main()
