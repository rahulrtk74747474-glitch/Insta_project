"""Independent Hindi-Neural voice demo (not OpenAI or OmniVoice).

Requires an Internet-accessible Microsoft Edge speech endpoint. Edge-TTS is
an unofficial client; stability and rights must be verified before production.
Only user-approved text is synthesized; never use eSpeak for final narration.
"""
import argparse,asyncio,json
from pathlib import Path
import edge_tts
async def generate(args):
    text=Path(args.script).read_text(encoding="utf-8").strip()
    if not text: raise ValueError("Narration script is empty")
    target=Path(args.output)
    target.parent.mkdir(parents=True,exist_ok=True)
    # Official Edge public Hindi neural voice names as of 2026; may change.
    speaker=edge_tts.Communicate(text,voice=args.voice,rate=args.rate)
    await speaker.save(str(target))
    if target.stat().st_size < 1000: raise RuntimeError("No usable audio returned")
    print(json.dumps({"output":str(target),"bytes":target.stat().st_size,
                      "voice":args.voice,"chars":len(text)},ensure_ascii=False))
if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--script",default="examples/original_time_loop_hindi_narration.txt")
    p.add_argument("--output",default="dist/natural_hindi_voice.mp3")
    p.add_argument("--voice",default="hi-IN-MadhurNeural")
    p.add_argument("--rate",default="-2%")
    asyncio.run(generate(p.parse_args()))
