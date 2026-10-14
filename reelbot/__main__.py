"""CLI: dry-run a storyboard, or process one approved queue entry."""
import argparse
import json
import os
import sys
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
from .render import render
from .publish import require_credentials, instagram_reel, youtube_short


def save_queue(file,data):
    file=Path(file); file.parent.mkdir(parents=True,exist_ok=True)
    fd, name=tempfile.mkstemp(dir=file.parent,suffix=".json.tmp")
    try:
        with os.fdopen(fd,"w",encoding="utf-8") as out:
            json.dump(data,out,ensure_ascii=False,indent=2)
            out.write("\n")
        os.replace(name,file)
    finally:
        if os.path.exists(name):os.unlink(name)


def select(queue):
    for item in queue.get("items",[]):
        if item.get("status") not in ("queued","partial"):
            continue
        if not item.get("rights_confirmed",False):
            continue
        if not item.get("storyboard"):
            continue
        return item
    return None


def wait_until(hour="19:00",timezone="Asia/Kolkata"):
    now=datetime.now(ZoneInfo(timezone))
    h,m=[int(x) for x in hour.split(":")]
    target=now.replace(hour=h,minute=m,second=0,microsecond=0)
    seconds=(target-now).total_seconds()
    if seconds< -1800:
        raise RuntimeError("Publishing window missed; do not post unexpectedly late")
    if seconds>3600:
        raise RuntimeError("Schedule invoked too early; refusing to hold runner for hours")
    if seconds>0:time.sleep(seconds)


def main(argv=None):
    p=argparse.ArgumentParser(description="Storyboard-based Hindi reel automation")
    src=p.add_mutually_exclusive_group(required=True)
    src.add_argument("--storyboard",type=Path,help="Dry-run storyboard (never publish)")
    src.add_argument("--queue",type=Path,help="Process earliest approved item")
    p.add_argument("--output",type=Path,default=Path("dist/reel.mp4"))
    p.add_argument("--voice",type=Path,help="User-provided narration WAV or MP3")
    p.add_argument("--publish",action="store_true",help="Use connected official platform APIs")
    p.add_argument("--wait-until-7pm",action="store_true",help="Wait until 19:00 Asia/Kolkata before uploading")
    args=p.parse_args(argv)
    if args.storyboard:
        if args.publish:raise SystemExit("Publishing is only available with --queue and approved rights.")
        print(json.dumps(render(args.storyboard,args.output,args.voice),ensure_ascii=False))
        return 0
    queue_file=args.queue
    data=json.loads(queue_file.read_text(encoding="utf-8"))
    item=select(data)
    if item is None:
        print("No approved, unprocessed storyboard in the queue; nothing published.")
        return 0
    if args.publish:
        if os.environ.get("ENABLE_AUTOPUBLISH")!="true":
            raise SystemExit("Set ENABLE_AUTOPUBLISH=true as a separate publish gate.")
        require_credentials()
    # Resolve paths relative to repository root (queue lives in data/).
    root=queue_file.resolve().parent.parent
    source=(root/item["storyboard"]).resolve()
    if not source.is_file():raise FileNotFoundError(source)
    print(json.dumps(render(source,args.output,args.voice),ensure_ascii=False))
    if not args.publish:
        print("Dry run only. Queue not modified; video not posted.")
        return 0
    if args.wait_until_7pm:wait_until()
    posted=item.setdefault("posted",{})
    item["status"]="partial"
    # Persist each successful upload separately to reduce risk of duplicate posts on retry.
    if not posted.get("instagram"):
        result=instagram_reel(args.output,item.get("description",""))
        posted["instagram"]=result
        save_queue(queue_file,data)
        print("Instagram:",result.get("url") or result["id"])
    if not posted.get("youtube"):
        result=youtube_short(args.output,item.get("title","Hindi Study Reel"),
                             item.get("description",""))
        posted["youtube"]=result
        save_queue(queue_file,data)
        print("YouTube:",result["url"],"privacy:",result["privacy"])
    item["status"]="published"
    item["published_at"]=datetime.now(ZoneInfo("Asia/Kolkata")).isoformat()
    save_queue(queue_file,data)
    return 0


if __name__=="__main__":
    sys.exit(main())
