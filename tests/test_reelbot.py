"""Dependency-free queue validation checks (CI can run with unittest)."""
import json
import tempfile
import unittest
from pathlib import Path
from reelbot.__main__ import select, save_queue
from reelbot.render import font, card_base, art_layer


class ReelTests(unittest.TestCase):
    def test_queue_requires_rights(self):
        self.assertIsNone(select({"items":[{"status":"queued","rights_confirmed":False,"storyboard":"x"}]}))
        self.assertIsNone(select({"items":[{"status":"queued","rights_confirmed":True}]}))
        self.assertEqual(select({"items":[{"status":"queued","rights_confirmed":True,"storyboard":"x"}]})["storyboard"],"x")

    def test_atomic_queue_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/"queue.json"
            save_queue(p,{"items":[{"title":"हिंदी"}]})
            self.assertEqual(json.loads(p.read_text(encoding="utf8"))["items"][0]["title"],"हिंदी")

    def test_storyboard_drawing(self):
        scene={"art":"book","title":"पढ़ें","overlay":"समझें","narration":"पहले समझिए"}
        self.assertEqual(art_layer(scene).size,(720,590))
        self.assertEqual(card_base(scene,1,7).size,(720,1280))

    def test_sample_manifest(self):
        data=json.loads(Path("data/storyboards/time_loop.json").read_text(encoding="utf8"))
        self.assertEqual(len(data["scenes"]),7)
        self.assertTrue(all(s["duration_sec"]>3 for s in data["scenes"]))


if __name__=="__main__":
    unittest.main()
