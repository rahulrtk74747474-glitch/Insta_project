"""Independent public Hindi neural-voice preview with speech-aligned words.

IMPORTANT: Edge-TTS is unofficial and depends on Microsoft's speech endpoint.
No user audio uploaded and no automatic publishing. Word timings are returned
by the service and used to create SRT for user review.
"""
import argparse,asyncio,json,re
from pathlib import Path
import edge_tts

def srt_time(s):
    ms=max(0,round(s*1000))
    hh,ms=divmod(ms,3600000); mm,ms=divmod(ms,60000); ss,ms=divmod(ms,1000)
    return f"{hh:02}:{mm:02}:{ss:02},{ms:03}"

def group_captions(words,max_chars=57,max_seconds=4.2):
    clips=[];buff=[]
    for item in words:
        piece=item["text"].strip()
        if not piece:continue
        if buff and (sum(len(x["text"])+1 for x in buff)+len(piece)>max_chars or
                     item["start"]-buff[0]["start"]>max_seconds or
                     item["start"]-buff[-1]["end"]>0.8):
            clips.append(buff);buff=[]
        buff.append(item)
        if piece.endswith(("।","!","?")) and len(" ".join(x["text"] for x in buff))>=28:
            clips.append(buff);buff=[]
    if buff:clips.append(buff)
    out=[]
    for idx,grp in enumerate(clips):
        start=grp[0]["start"]
        end=grp[-1]["end"]+.13
        if idx<len(clips)-1:end=min(end,clips[idx+1][0]["start"] if clips[idx+1] else end)
        out.append({"id":idx+1,"start":max(0,start),"end":max(start+.1,end),
                    "text":" ".join(x["text"].strip() for x in grp)})
    return out

async def generate(args):
    text=Path(args.script).read_text(encoding="utf-8").strip()
    if not text:raise ValueError("Narration script is empty")
    target=Path(args.output)
    target.parent.mkdir(parents=True,exist_ok=True)
    speaker=edge_tts.Communicate(text,voice=args.voice,rate=args.rate)
    words=[]
    with target.open("wb") as audio:
        async for chunk in speaker.stream():
            if chunk["type"]=="audio":
                audio.write(chunk["data"])
            elif chunk["type"]=="WordBoundary":
                words.append({
                    "start":chunk["offset"]/10000000,
                    "end":(chunk["offset"]+chunk["duration"])/10000000,
                    "text":chunk["text"]})
    if target.stat().st_size<1000:raise RuntimeError("No usable audio returned")
    if len(words)<100:
        raise RuntimeError(f"Only {len(words)} word boundary events; cannot ensure subtitle synchronization")
    captions=group_captions(words)
    srt=target.with_suffix(".srt")
    srt.write_text("".join(
        f"{x['id']}\n{srt_time(x['start'])} --> {srt_time(x['end'])}\n{x['text']}\n\n"
        for x in captions),encoding="utf-8")
    report={"output":str(target),"bytes":target.stat().st_size,
            "voice":args.voice,"characters":len(text),"words_with_timing":len(words),
            "caption_cues":len(captions),"last_word_end":round(words[-1]["end"],3)}
    target.with_suffix(".json").write_text(json.dumps(
        {"report":report,"words":words,"captions":captions},ensure_ascii=False,indent=2),
        encoding="utf-8")
    print(json.dumps(report,ensure_ascii=False))

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--script",default="examples/original_time_loop_hindi_narration.txt")
    p.add_argument("--output",default="dist/natural_hindi_voice.mp3")
    p.add_argument("--voice",default="hi-IN-MadhurNeural")
    p.add_argument("--rate",default="-2%")
    asyncio.run(generate(p.parse_args()))
