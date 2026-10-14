# Stage 2 — English transcription, preserving Stage 1

Development branch: `feature/stage2-english-transcription` (created from the Stage 1 checkpoint). **No translation, voice synthesis or publishing in this stage.**

## Input / output

Input: existing Stage 1 SQLite job and `ingest/vocals.wav` (when separated) or `ingest/audio.wav` (original mixed audio when Demucs weights were unavailable). Stage 2 **does not claim vocals were isolated** if the original mix is used.

Files under `output/<job_id>/transcribe/`:

- `english.json` — English captions and all usable word-level timestamps, model/source info.
- `english.srt` — readable punctuation- and time-split captions.
- `asr_report.json` — automatic counts, source quality flag and warnings.

SQLite table `stage_runs` keeps per-stage attempt/status/error/results; a repeated run skips Stage 2 when its output exists.

## Run against your existing saved Stage 1 job

Check out the Stage 2 branch and install Python requirements (Python 3.11), including `faster-whisper` and FFmpeg. Model downloads require internet the first time.

```bash
python -m pip install -r requirements.txt
python run.py --resume <job_id> --until transcribe
```

If the earlier Stage 1 run was made only in a temporary environment and its SQLite database/files do not exist in your current checkout, first import the *authorized* local MP4 as a **new local Stage 1 job**:

```bash
# Only for this test: skip voice separation if Demucs model weights cannot download.
# Make a copy of config.yaml as config.test.yaml and set demucs.enabled: false there.
python run.py --config config.test.yaml --file input/owned_video.mp4 --rights-confirmed --until transcribe
```

To force-retry only Stage 2 after editing the model or captions:

```bash
python run.py --resume <job_id> --force-stage transcribe --until transcribe
```

To test on CPU with a smaller model, set `whisper.model: tiny.en`, `whisper.device: cpu`, and `whisper.compute_type: int8` in a test copy of config.yaml. `small.en` is the normal starting configuration. Transcription of a 4m53s video can be slow on CPU.

### Test / review

```bash
python -m unittest discover -s tests -p 'test_stage2.py' -v
python -m unittest discover -s tests -p 'test_pipeline.py' -v
python run.py --list-jobs
```

Verify every cue has a start before end, the English SRT is readable, and `english.json` includes word-level timestamps. The report labels original mixed audio (no Demucs stems) and any timestamp warnings. Whisper accuracy is model-dependent; don't assume it is a human-approved transcript.

### Live end-to-end synthetic speech smoke

A separate GitHub Actions job installs `faster-whisper`, downloads the `tiny.en` model, synthesizes **its own** short English test phrase with eSpeak, and runs the actual word-timestamp transcription. This verifies model dependencies but does **not** transcribe the user's private video. No third-party source video is stored in the public repository.

## Stage 1 checkpoint

- Process: [01_ingest_test_process.md](01_ingest_test_process.md).
- Measurement report: [../../reports/stage1/stage1_report.json](../../reports/stage1/stage1_report.json).
- FFmpeg extraction/resume passed. Demucs could not download model weights in the previous runtime, so its quality remains **unverified**. Stage 2 can proceed on original mixed audio but must flag this condition.

## Security and scope

Nothing is uploaded or posted anywhere. Do not check in customer/user video or API keys. No .env credentials are required to test Stage 2, and Stage 3 translation is not invoked.

## Recorded result: actual uploaded study video

A real local CPU transcription was completed on the supplied 4m53.48s MP4, using the Stage 1 audio. The MP4, extracted WAV and full transcript were **not pushed to the public repository**. Only aggregate metrics appear in [reports/stage2/stage2_actual_video_test.json](../../reports/stage2/stage2_actual_video_test.json).

- Faster-Whisper `tiny.en`, CPU int8, 48 original ASR segments.
- 741 English word tokens with timestamps; **19 zero-length token timings preserved with explicitly flagged 10ms estimates**.
- 120 readable SRT cues after time/punctuation splitting; timestamps monotonic, no overlap, final cue at 292.84 seconds.
- Stage 2 in SQLite: completed; second invocation skipped successfully without another ASR run.
- Stage 3: pending; no Hindi translation or publishing.
- Known limitation: Demucs stems were unavailable during Stage 1, so ASR used original mixed audio. No reference transcript was provided, so word-error rate is unknown.

### Dependency compatibility note

Under Python 3.13, unpinned PyAV 19 raised `TypeError: open() got an unexpected keyword argument 'metadata_errors'` inside Faster-Whisper 1.2.1. A compatible PyAV 18.1.0 wheel fixed this, and `requirements.txt` now constrains `av>=11,<19`. GitHub Actions also ran a real Faster-Whisper `tiny.en` smoke test with its own synthetic English recording.

### Direct quick test for a new video

Use `config.stage2_cpu.yaml` (Demucs disabled, Whisper `tiny.en`, CPU int8) only as a development mode:

```bash
python run.py --config config.stage2_cpu.yaml --file input/owned_video.mp4 --rights-confirmed --until transcribe
```

The output JSON displays the job ID. Inspect `output/<job_id>/transcribe/english.srt`, `english.json` and `asr_report.json`. For better recognition accuracy once the quick test passes, replace `tiny.en` with `small.en` (slower/higher memory).
