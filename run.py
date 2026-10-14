"""Resumable rights-checked pipeline CLI: English ingest through Hindi MP4 preview; manual publishing."""
from __future__ import annotations
import argparse,json,sys
from pathlib import Path
from dotenv import load_dotenv
import yaml
from hindi_pipeline.common import STAGES,setup_logging
from hindi_pipeline.orchestrator import Pipeline

def main(argv=None):
    p=argparse.ArgumentParser(description="Authorized English video to reviewable Hindi MP4; stages 1-5, NO uploads")
    group=p.add_mutually_exclusive_group(required=True)
    group.add_argument("--url")
    group.add_argument("--file",type=Path)
    group.add_argument("--resume")
    group.add_argument("--list-jobs",action="store_true")
    p.add_argument("--rights-confirmed",action="store_true")
    p.add_argument("--until",choices=STAGES,default="translate")
    p.add_argument("--force-stage",choices=STAGES)
    p.add_argument("--config",type=Path,default=Path("config.yaml"))
    args=p.parse_args(argv)
    load_dotenv();setup_logging()
    config=yaml.safe_load(args.config.read_text(encoding="utf-8"))
    pipeline=Pipeline(config)
    if args.list_jobs:
        print(json.dumps(pipeline.db.list(),ensure_ascii=False,indent=2));return 0
    id=args.resume if args.resume else pipeline.create(
        str(args.file if args.file else args.url),"local" if args.file else "url",args.rights_confirmed)
    result=pipeline.process(id,args.until,args.force_stage)
    print(json.dumps({"job_id":id,"output":result["output"],"stages":[
          {"name":s["stage"],"status":s["status"],"attempts":s["attempts"],"result":s["result"]}
          for s in result["stages"]]},ensure_ascii=False,indent=2))
    return 0
if __name__=="__main__":sys.exit(main())
