"""SQLite jobs and one row per stage per video."""
from __future__ import annotations
import json, sqlite3
from datetime import datetime, timezone
from pathlib import Path
from .common import STAGES

def utc():return datetime.now(timezone.utc).isoformat()

class JobDB:
    def __init__(self,path:Path):
        path.parent.mkdir(parents=True,exist_ok=True)
        self.conn=sqlite3.connect(path)
        self.conn.row_factory=sqlite3.Row
        self.conn.execute("PRAGMA busy_timeout=30000")
        self.conn.executescript("""
        CREATE TABLE IF NOT EXISTS jobs (
            id TEXT PRIMARY KEY, source TEXT NOT NULL, source_type TEXT NOT NULL,
            rights_confirmed INTEGER NOT NULL CHECK(rights_confirmed=1),
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS stage_runs (
            job_id TEXT NOT NULL REFERENCES jobs(id),stage TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',attempts INTEGER NOT NULL DEFAULT 0,
            result_json TEXT,error TEXT,started_at TEXT,finished_at TEXT,
            PRIMARY KEY(job_id,stage)
        );
        """)
        self.conn.commit()
    def add(self,id,source,mode):
        with self.conn:
            self.conn.execute("INSERT OR IGNORE INTO jobs VALUES(?,?,?,?,?,?)",(id,source,mode,1,utc(),utc()))
            for name in STAGES:
                self.conn.execute("INSERT OR IGNORE INTO stage_runs(job_id,stage) VALUES(?,?)",(id,name))
    def job(self,id):
        row=self.conn.execute("SELECT * FROM jobs WHERE id=?",(id,)).fetchone()
        if not row:raise ValueError(f"Unknown job {id}")
        return dict(row)
    def stage(self,id,name):
        row=self.conn.execute("SELECT * FROM stage_runs WHERE job_id=? AND stage=?",(id,name)).fetchone()
        if not row:raise ValueError(f"Unknown stage {name}")
        result=dict(row)
        result["result"]=json.loads(result["result_json"]) if result["result_json"] else None
        return result
    def start(self,id,name):
        with self.conn:
            self.conn.execute("UPDATE stage_runs SET status='running',attempts=attempts+1,started_at=?,finished_at=NULL,error=NULL WHERE job_id=? AND stage=?",(utc(),id,name))
    def finish(self,id,name,result):
        with self.conn:
            self.conn.execute("UPDATE stage_runs SET status='completed',result_json=?,error=NULL,finished_at=? WHERE job_id=? AND stage=?",(json.dumps(result,ensure_ascii=False),utc(),id,name))
            self.conn.execute("UPDATE jobs SET updated_at=? WHERE id=?",(utc(),id))
    def fail(self,id,name,exc):
        with self.conn:
            self.conn.execute("UPDATE stage_runs SET status='failed',error=?,finished_at=? WHERE job_id=? AND stage=?",(str(exc)[:3000],utc(),id,name))
    def stages(self,id):return [self.stage(id,name) for name in STAGES]
    def list(self):return [dict(row) for row in self.conn.execute("SELECT * FROM jobs ORDER BY created_at DESC")]
