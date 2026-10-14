"""Render BOTH Hindi review videos from authorized local source and new narration.

This is the Stage 6 independent adapter for videos whose Hindi neural narration
is longer/shorter than the English original. It preserves video content by
adjusting the visual presentation clock, not by speeding up speech. No upload.
"""
from __future__ import annotations
import argparse, json, os, subprocess
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont

def duration(path):
    return float(subprocess.check_output(["ffprobe","-v","error",
        "-show_entries","format=duration","-of","default=noprint_wrappers=1:nokey=1",
        str(path)],text=True).strip())

def graphics(where):
    where.mkdir(parents=True,exist_ok=True)
    family="/usr/share/fonts/truetype/noto/NotoSansDevanagari-Bold.ttf"
    if not Path(family).exists():
        raise RuntimeError("Install fonts-noto-core for readable Hindi graphics")
    eng="/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    def hi(n):return ImageFont.truetype(family,n)
    def en(n):return ImageFont.truetype(eng,n)
    l=Image.new("RGBA",(1280,720));d=ImageDraw.Draw(l)
    d.rounded_rectangle((20,22,390,104),radius=22,fill=(12,23,40,220),
                        outline=(57,217,191,180),width=2)
    d.text((43,32),"TIME LOOP  •  STUDY SMART",font=en(19),fill="white")
    d.text((43,57),"हिंदी एक्सप्लेनर",font=hi(23),fill="white")
    for y in range(555,720):
        d.line((0,y,1280,y),fill=(6,12,21,int((y-555)/165*175)))
    lp=where/"overlay_landscape.png";l.save(lp)
    p=Image.new("RGBA",(720,1280));d=ImageDraw.Draw(p)
    d.rounded_rectangle((24,35,696,171),radius=36,
                        fill=(4,19,33,225),outline=(57,217,191,220),width=3)
    d.text((50,44),"STUDY SMART  /  HINDI",font=en(27),fill=(85,246,210))
    d.text((50,87),"टाइम लूप मेथड",font=hi(42),fill="white")
    d.rounded_rectangle((5,238,714,646),radius=15,outline=(113,239,218,220),width=4)
    d.rounded_rectangle((22,672,698,796),radius=30,
                        fill=(4,15,28,220),outline=(52,221,182,190),width=2)
    d.text((51,690),"स्मार्ट पढ़ाई की 3 ट्रिक्स",font=hi(38),fill="white")
    d.text((51,747),"RECALL  •  REVIEW  •  PRACTICE",font=en(18),fill=(90,226,205))
    d.rounded_rectangle((25,1155,695,1245),radius=24,fill=(7,20,34,207))
    d.text((52,1173),"सीखो  •  याद करो  •  दोहराओ",font=hi(28),fill=(170,250,233))
    pp=where/"overlay_portrait.png";p.save(pp)
    return pp,lp

def render(args):
    source=Path(args.source).resolve()
    voice=Path(args.voice).resolve()
    captions=Path(args.subtitles).resolve()
    for p in [source,voice,captions]:
        if not p.is_file(): raise FileNotFoundError(str(p))
    out=Path(args.output_dir).resolve();out.mkdir(parents=True,exist_ok=True)
    pp,lp=graphics(out)
    vd,ad=duration(source),duration(voice)
    if not 0.5 < ad/vd < 2.0:
        raise ValueError("Hindi/English lengths differ too much; check the voice file")
    ratio=ad/vd
    # Safe known absolute path, FFmpeg filter accepts no untrusted shell, all argv literal.
    # Copy to simple ASCII basename to avoid quoting issues inside libass.
    srt=out/"review_subtitles.srt"
    import shutil
    shutil.copy2(captions,srt)
    results={}
    for variant,overlay in (("portrait",pp),("landscape",lp)):
        target=out/f"final_hindi_{variant}.mp4"
        if variant=="portrait":
            vf=(f"[0:v]setpts={ratio:.9f}*(PTS-STARTPTS),fps=24,"
                "split=2[blur][fg0];"
                "[blur]scale=720:1280:force_original_aspect_ratio=increase,"
                "crop=720:1280,boxblur=9:1,eq=brightness=-0.16:saturation=0.65[bg];"
                "[fg0]scale=704:-2:flags=bicubic[fg];"
                "[bg][fg]overlay=8:244[base];"
                "[base][2:v]overlay=0:0:shortest=1,"
                "subtitles=filename=review_subtitles.srt:"
                "force_style='FontName=Noto Sans Devanagari,FontSize=33,"
                "PrimaryColour=&H00FFFFFF,OutlineColour=&H00101922,"
                "Outline=3,Shadow=0,Alignment=2,MarginV=255'[out]")
        else:
            vf=(f"[0:v]setpts={ratio:.9f}*(PTS-STARTPTS),fps=24,scale=1280:720[bg];"
                "[bg][2:v]overlay=0:0:shortest=1,"
                "subtitles=filename=review_subtitles.srt:"
                "force_style='FontName=Noto Sans Devanagari,FontSize=29,"
                "PrimaryColour=&H00FFFFFF,OutlineColour=&H0008151B,"
                "Outline=3,Shadow=1,Alignment=2,MarginV=60'[out]")
        cmd=["ffmpeg","-hide_banner","-loglevel","error","-y",
             "-i",str(source),"-i",str(voice),"-loop","1","-framerate","24",
             "-i",str(overlay),"-filter_complex",vf,
             "-map","[out]","-map","1:a:0","-t",f"{ad:.3f}",
             "-r","24","-c:v","libx264","-preset","veryfast","-crf","24",
             "-pix_fmt","yuv420p","-c:a","aac","-b:a","128k",
             "-movflags","+faststart",str(target)]
        subprocess.run(cmd,cwd=out,check=True,timeout=2400)
        if not target.is_file() or abs(duration(target)-ad)>0.6:
            raise RuntimeError("Final video failed duration validation")
        results[variant]=str(target)
    report={"status":"review_only","voice_duration_s":round(ad,3),
            "original_duration_s":round(vd,3),
            "visual_timing_ratio":round(ratio,4),"original_english_audio_used":False,
            "subtitles":"provided separately; verify alignment quality",
            "published":False,"outputs":results}
    (out/"final_review.json").write_text(
        json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(report,ensure_ascii=False,indent=2))
if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--source",required=True)
    p.add_argument("--voice",required=True)
    p.add_argument("--subtitles",required=True)
    p.add_argument("--output-dir",default="dist/final_hindi_review")
    render(p.parse_args())
