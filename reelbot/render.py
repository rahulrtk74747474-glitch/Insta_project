"""Deterministic storyboard-to-short-video renderer. Uses original art or editable keyframes."""
from __future__ import annotations

import json
import math
import shutil
import subprocess
import tempfile
import wave
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageOps

W, H = 720, 1280
PAPER, INK = "#FFF9EA", "#243046"
BLUE, CORAL, TEAL, YELLOW, GREEN = "#3C7DE0", "#F27565", "#3CB39D", "#FFD46B", "#79BC5A"
WHITE = "#FFFFFF"


def run(*args):
    subprocess.run([str(x) for x in args], check=True, stdout=subprocess.DEVNULL)


def font(size: int, bold: bool = False):
    paths = [
        "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Bold.ttf" if bold
        else "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Regular.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for p in paths:
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def wrap(draw, message, x, y, width, size=32, color=INK, bold=False, spacing=14, limit=4):
    ft = font(size, bold)
    lines, cur = [], ""
    for word in message.split():
        proposal = (cur + " " + word).strip()
        if draw.textbbox((0, 0), proposal, font=ft)[2] > width and cur:
            lines.append(cur)
            cur = word
        else:
            cur = proposal
    if cur:
        lines.append(cur)
    for line in lines[:limit]:
        draw.text((x, y), line, font=ft, fill=color)
        y += size + spacing
    return y


def circle(draw, xy, r, fill, outline=INK, line=5):
    x, y = xy
    draw.ellipse((x-r, y-r, x+r, y+r), fill=fill, outline=outline, width=line)


def sketch_character(d, x=210, y=180, scale=1.0):
    r = int(64 * scale)
    circle(d, (x, y), r, "#FBE0C2", INK, 6)
    d.pieslice((x-r+5, y-r-12, x+r-5, y+r-35), 180, 350, fill=INK)
    circle(d, (int(x-21*scale), int(y)), max(2,int(5*scale)), INK, INK, 1)
    circle(d, (int(x+22*scale), int(y)), max(2,int(5*scale)), INK, INK, 1)
    d.arc((x-22, y+4, x+24, y+35), 12, 168, fill=CORAL, width=4)
    d.rounded_rectangle((x-int(73*scale),y+r+8,x+int(73*scale),y+r+int(152*scale)),radius=30,fill=BLUE,outline=INK,width=5)
    d.line((x-72,y+r+60,x-125,y+r+130), fill=INK, width=6)
    d.line((x+72,y+r+60,x+125,y+r+130), fill=INK, width=6)


def art_layer(scene):
    im = Image.new("RGBA", (W, 590))
    d = ImageDraw.Draw(im)
    kind = scene.get("art", "student")
    if kind == "student":
        sketch_character(d, 235, 200, 1)
        d.line((60, 490, 515, 490), fill=INK, width=9)
        d.polygon([(105,448),(255,426),(306,485),(150,490)],fill=WHITE,outline=INK,width=5)
        circle(d,(535,230),85,"#FFFFFF")
        wrap(d,"?",515,175,80,85,CORAL,True)
        for xy in [(450,95),(575,85),(610,315)]:
            circle(d,xy,14,YELLOW,INK,2)
    elif kind == "book":
        d.polygon([(75,240),(332,285),(332,515),(75,472)],fill="#D9F7D5",outline=INK)
        d.polygon([(645,240),(388,285),(388,515),(645,472)],fill="#EFFAFB",outline=INK)
        for p in [[(75,240),(332,285),(332,515),(75,472),(75,240)],[(645,240),(388,285),(388,515),(645,472),(645,240)]]:
            d.line(p,fill=INK,width=6,joint="curve")
        for k in range(4):
            d.line((110,310+k*42,296,340+k*32),fill=TEAL,width=5)
            d.line((420,340+k*32,606,310+k*42),fill=BLUE,width=5)
        circle(d,(360,135),84,YELLOW)
        d.rectangle((330,214,387,251),fill=INK)
        for x,y in [(200,95),(515,95),(360,20)]:
            d.line((x,y,x+10,y+42),fill=CORAL,width=8)
    elif kind == "recall":
        d.rounded_rectangle((145,108,570,525),radius=35,fill=WHITE,outline=INK,width=6)
        for k in range(6):
            d.line((210,240+42*k,520,240+42*k),fill="#B9C9D1",width=5)
        d.ellipse((260,90,465,252),outline=CORAL,width=9,fill="#FFE1DB")
        for x in (310,355,415):
            d.arc((x-35,135,x+30,225),0,270,fill=TEAL,width=7)
        d.line((490,455,548,393),fill=BLUE,width=16)
        d.polygon([(547,384),(570,367),(554,405)],fill=INK)
        wrap(d,"?",336,122,55,55,INK,True)
    elif kind == "calendar":
        d.rounded_rectangle((70,100,650,525),radius=35,fill=WHITE,outline=INK,width=6)
        d.rounded_rectangle((74,104,646,194),radius=30,fill="#C9F5EB")
        for j,(num,xy,color) in enumerate(zip(["0","1","3","7","14"],[(158,280),(360,280),(562,280),(262,427),(458,427)],[CORAL,TEAL,BLUE,GREEN,YELLOW])):
            circle(d,xy,62,color)
            bb=d.textbbox((0,0),num,font=font(43,True))
            d.text((xy[0]-(bb[2]-bb[0])/2,xy[1]-35),num,font=font(43,True),fill=INK)
        d.line((165,110,165,170),fill=CORAL,width=12)
        d.line((545,110,545,170),fill=CORAL,width=12)
    elif kind == "quiz":
        d.rounded_rectangle((142,72,575,545),radius=30,fill=WHITE,outline=INK,width=6)
        d.rounded_rectangle((245,56,475,126),radius=14,fill=YELLOW,outline=INK,width=4)
        for k in range(5):
            y=175+k*70
            d.rectangle((190,y,238,y+43),outline=INK,width=4)
            d.line((266,y+20,512,y+20),fill="#A6B1C2",width=5)
            c=GREEN if k<4 else CORAL
            if k<4:
                d.line([(199,y+24),(214,y+36),(235,y+10)],fill=c,width=7)
            else:
                d.line([(199,y+10),(232,y+36)],fill=c,width=7)
                d.line([(232,y+10),(199,y+36)],fill=c,width=7)
        circle(d,(101,175),35,YELLOW)
    elif kind == "palace":
        d.polygon([(95,225),(360,55),(630,225)],fill="#F5CB85",outline=INK)
        d.rectangle((130,226,585,530),fill="#FFFDF6",outline=INK,width=7)
        d.rectangle((200,358,410,450),fill=BLUE,outline=INK,width=5)
        d.rectangle((475,342,555,470),fill="#B6E3C9",outline=INK,width=5)
        d.rectangle((150,310,220,364),fill=YELLOW,outline=INK,width=4)
        d.rectangle((300,260,390,318),fill=CORAL,outline=INK,width=4)
        for x,y,txt,col in [(175,155,"A",CORAL),(500,196,"B",TEAL),(340,360,"C",YELLOW)]:
            circle(d,(x,y),29,col)
            d.text((x-13,y-27),txt,font=font(32,True),fill=INK)
    else:
        circle(d,(225,260),124,"#D7F5EA")
        circle(d,(500,260),124,"#FFE6CD")
        d.arc((120,82,603,455),215,352,fill=CORAL,width=13)
        d.arc((120,82,603,455),20,152,fill=TEAL,width=13)
        wrap(d,"1",206,202,70,80,BLUE,True)
        wrap(d,"2",475,202,70,80,CORAL,True)
        d.line([(574,115),(609,143),(569,158)],fill=INK,width=9)
        d.line([(145,416),(102,392),(148,373)],fill=INK,width=9)
        d.polygon([(281,530),(359,567),(450,530)],fill=YELLOW,outline=INK)
    return im


def card_base(scene, pos, count):
    bg = Image.new("RGB",(W,H),PAPER)
    d=ImageDraw.Draw(bg)
    d.rounded_rectangle((28,25,692,1255),radius=40,fill=WHITE,outline="#E4DECE",width=4)
    d.rounded_rectangle((65,62,300,120),radius=17,fill=INK)
    d.text((86,76),"HINDI DOODLE",font=font(22,True),fill=WHITE)
    d.rounded_rectangle((552,62,650,120),radius=17,fill="#FFF0C6")
    d.text((575,76),f"{pos+1}/{count}",font=font(22,True),fill=INK)
    wrap(d,scene.get("title","अगला कदम"),75,160,567,50,INK,True,14,2)
    d.rounded_rectangle((72,301,648,381),radius=22,fill="#DEF5ED")
    wrap(d,scene.get("overlay",""),92,319,530,29,TEAL,True,7,2)
    d.rounded_rectangle((70,430,650,1003),radius=36,fill="#F9F3E6",outline="#E9E0D0",width=3)
    d.rounded_rectangle((70,1040,650,1178),radius=22,fill=WHITE,outline="#E5DECD",width=3)
    wrap(d,scene.get("narration",""),94,1060,533,32,INK,False,8,3)
    for n in range(count):
        d.rounded_rectangle((83+n*80,1202,132+n*80,1216),radius=6,fill=CORAL if n<=pos else "#E5DFD5")
    return bg


def prepare_voice(scenes, dest):
    """Return the temporary espeak WAV and exact per-scene durations."""
    if shutil.which("espeak") is None:
        raise RuntimeError("espeak is required for temporary Hindi narration; or pass --voice")
    pieces, durations = [], []
    fmt = None
    for i,sc in enumerate(scenes):
        p=dest/f"voice_{i+1:02d}.wav"
        run("espeak","-v","hi","-s","141","-w",p,sc["narration"])
        with wave.open(str(p),"rb") as f:
            info=(f.getframerate(),f.getnchannels(),f.getsampwidth())
            if fmt is None: fmt=info
            if fmt!=info: raise ValueError("inconsistent voice audio formats")
            dat=f.readframes(f.getnframes())
            silence=b"\0" * round(.82*info[0])*info[1]*info[2]
            pieces.append(dat+silence)
            durations.append((len(dat)+len(silence))/(info[0]*info[1]*info[2]))
    path=dest/"voice.wav"
    with wave.open(str(path),"wb") as f:
        f.setframerate(fmt[0]);f.setnchannels(fmt[1]);f.setsampwidth(fmt[2])
        f.writeframes(b"".join(pieces))
    return path,durations


def duration(path):
    p=subprocess.run(["ffprobe","-v","error","-show_entries","format=duration","-of","default=noprint_wrappers=1:nokey=1",str(path)],capture_output=True,text=True,check=True)
    return float(p.stdout.strip())


def render(storyboard, output, voice=None):
    storyboard=Path(storyboard)
    data=json.loads(storyboard.read_text(encoding="utf-8"))
    scenes=data["scenes"]
    if not scenes or any(float(sc.get("duration_sec",0))<=0 for sc in scenes):
        raise ValueError("storyboard must have scenes with positive durations")
    output=Path(output);output.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="reelbot_") as tmp:
        work=Path(tmp)
        if voice:
            voice=Path(voice)
            if not voice.is_file():raise FileNotFoundError(voice)
            total=duration(voice)
            orig=sum(float(s["duration_sec"]) for s in scenes)
            durs=[total*float(s["duration_sec"])/orig for s in scenes]
            sound=voice
        else:
            sound,durs=prepare_voice(scenes,work)
        clips=[]
        for i,(scene,dur) in enumerate(zip(scenes,durs)):
            art_path=scene.get("image")
            if art_path:
                art_file=(storyboard.parent/art_path).resolve()
                if not art_file.is_file():raise FileNotFoundError(art_file)
                art=ImageOps.fit(Image.open(art_file).convert("RGBA"),(W,590))
            else:
                art=art_layer(scene)
            base=card_base(scene,i,len(scenes))
            frame_paths=[]
            for step in range(9):
                a=base.copy()
                mask=Image.new("L", art.size,0)
                ImageDraw.Draw(mask).rectangle((0,0,int(W*(step+1)/9),590),fill=255)
                drawing=art.copy();drawing.putalpha(mask)
                a.paste(drawing,(0,416),drawing)
                frame=work/f"{i:02d}_{step:02d}.png"
                a.save(frame)
                frame_paths.append(frame)
            concat=work/f"scene_{i:02d}.ffconcat"
            with concat.open("w") as f:
                f.write("ffconcat version 1.0\n")
                short=min(.15,dur/12)
                for p in frame_paths[:-1]:
                    f.write(f"file '{p.as_posix()}'\nduration {short:.5f}\n")
                f.write(f"file '{frame_paths[-1].as_posix()}'\nduration {max(.1,dur-8*short):.5f}\n")
                f.write(f"file '{frame_paths[-1].as_posix()}'\n")
            clip=work/f"{scene.get('id', f'S{i+1:02d}')}.mp4"
            run("ffmpeg","-y","-loglevel","error","-safe","0","-f","concat","-i",concat,
                "-vf","fps=15,format=yuv420p","-c:v","libx264","-preset","veryfast",
                "-crf","23","-an",clip)
            clips.append(clip)
        merge=work/"clips.txt"
        merge.write_text("".join(f"file '{p.as_posix()}'\n" for p in clips))
        run("ffmpeg","-y","-loglevel","error","-safe","0","-f","concat","-i",merge,
            "-i",sound,"-map","0:v:0","-map","1:a:0","-c:v","copy","-c:a","aac",
            "-b:a","128k","-movflags","+faststart","-shortest",output)
    if not output.is_file() or output.stat().st_size < 1000:
        raise RuntimeError("video was not produced")
    return {"path":str(output),"seconds":duration(output),"scenes":len(scenes)}
