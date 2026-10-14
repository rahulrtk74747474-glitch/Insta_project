# Stage 1 — preserved ingestion test and process

This documents the earlier test of the user-provided 4m53s MP4. The video and extracted audio are **not committed** to this public repository. Code remains in `hindi_pipeline/ingest.py` and its resumable execution in `hindi_pipeline/orchestrator.py` and `hindi_pipeline/db.py`.

## Exact process

1. Confirm rights; `--rights-confirmed` is mandatory.
2. Run `python run.py --file /path/to/owned.mp4 --rights-confirmed --until ingest`.
3. FFmpeg generates 44.1 kHz stereo PCM `ingest/audio.wav`.
4. If Demucs is enabled, `python -m demucs -n htdemucs --two-stems=vocals` should produce `stems/htdemucs/audio/vocals.wav` and `no_vocals.wav`.
5. An unavailable model checkpoint is a **failure**, not a successful separation. SQLite records the failed attempt.
6. To test FFmpeg without model weights, use a *temporary configuration* with `demucs.enabled: false`. This uses original mixed audio, **not** isolated vocals.
7. Repeating an already completed run should skip it; after changing Demucs settings, explicitly force a re-run: `python run.py --resume <job_id> --force-stage ingest --until ingest`.

## Measured results

- Video integrity/copy: **PASS**, original SHA-256 and copy match.
- Source: MP4, H.264/AAC, 1280×720, duration **293.481 s**.
- FFmpeg extracted WAV: **PASS**, 44.1 kHz stereo, duration **293.399 s** (delta 0.083 s).
- Demucs stems: **BLOCKED**, local network could not download `htdemucs` weights, so stems were not created.
- SQLite failed → retry → completed (without separation) → skip: **PASS**, two stage attempts.
- Stage 2 and 3 were not run at the time of this report.

See `reports/stage1/stage1_report.json` for machine-readable evidence. Stage 1 remains a **PARTIAL PASS** until Demucs is tested on a machine that can download the model. Do not publish any content from this pipeline; manual publication only.
