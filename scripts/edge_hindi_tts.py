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
    if len(words)>=100:
        captions=group_captions(words)
        alignment="service_word_boundaries"
    else:
        # Some current Hindi voices emit no WordBoundary events. Report estimated
        # timing explicitly rather than failing after successfully creating audio.
        import subprocess
        result=subprocess.check_output([
            "ffprobe","-v","error","-show_entries","format=duration",
            "-of","default=noprint_wrappers=1:nokey=1",str(target)
        ],text=True)
        duration=float(result.strip())
        tokens=text.split()
        pieces=[]
        chunk=[]
        for token in tokens:
            if chunk and len(" ".join(chunk+[token]))>55:
                pieces.append(" ".join(chunk));chunk=[]
            chunk.append(token)
            if token.endswith(("।","!","?")) and len(" ".join(chunk))>25:
                pieces.append(" ".join(chunk));chunk=[]
        if chunk: pieces.append(" ".join(chunk))
        weights=[len(x)+(13 if x.endswith("।") else 0) for x in pieces]
        total=sum(weights)
        seconds=0
        captions=[]
        for i,(piece,weight) in enumerate(zip(pieces,weights),1):
            start=seconds
            seconds+=duration*weight/total
            captions.append({"id":i,"start":start,"end":seconds,"text":piece})
        alignment="estimated_from_text_length_no_word_boundaries"
    if not captions:
        raise RuntimeError("No Hindi subtitle cues could be generated")
    srt=target.with_suffix(".srt")
    srt.write_text("".join(
        f"{x['id']}\n{srt_time(x['start'])} --> {srt_time(x['end'])}\n{x['text']}\n\n"
        for x in captions),encoding="utf-8")
    report={"output":str(target),"bytes":target.stat().st_size,
            "voice":args.voice,"characters":len(text),"words_with_timing":len(words),
            "caption_cues":len(captions),"alignment":alignment,
            "last_word_end":round(words[-1]["end"],3) if words else None}
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
