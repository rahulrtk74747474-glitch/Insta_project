# Stage 3 — English to natural Hindi translation

Status: development branch feature/stage3-hindi-translation. Stages 1 and 2 are preserved. **This pipeline never publishes or uploads videos.**

## Architecture

The new provider hindi_pipeline/translate.py reads the approved Stage 2 transcribe/english.json (Option B: base.en plus caption optimizer). It sends groups of captions through the official OpenAI SDK using strict structured JSON output. It enforces glossary terms, rejects missing/duplicated IDs, retains source start/end values, and re-requests lines that are estimated to be too long for natural speech. Correct batches are cached with a content/model/config fingerprint and reused if a later API call fails.

Job output files under output/JOB_ID/translate/:
- hindi.srt — Hindi subtitles with precisely preserved English cue timestamps.
- hindi.json — Hindi text, original English, timing, estimated speech duration, glossary coverage.
- translation_report.json — quality metrics, model info, warnings, API calls, timing preservation.
- .staging/FINGERPRINT/batch_XXXX.json — local private resumable batch checkpoints.

The SQLite stage_runs record marks translate as completed only after successful output generation.

**Speech estimate caveat:** The timing fit is calculated from written Hindi length, NOT a recorded Hindi voice. Stage 4 must synthesize audio and fit timings. There is no measured semantic accuracy or back-translation QC yet.

## Setup

Use Python 3.11. First install requirements, and make a local .env:

    python3.11 -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt
    cp .env.example .env

Set OPENAI_API_KEY to your own valid API key within .env (ignored by git). The official SDK and hosted model may charge per token; do not commit API keys.

In config.yaml, Stage 2 remains whisper.provider: improved and whisper.model: base.en. Stage 3 defaults are translation.provider: openai, translation.model: gpt-4o-mini, translation.batch_size: 8, translation.max_quality_attempts: 3, translation.speed_tolerance: 1.15, and translation.glossary.

## Run and verify

When your previous Stage 2 job's SQLite database and English JSON are available locally:

    python run.py --resume JOB_ID --until translate

For a new authorized file:

    python run.py --file input/owned_video.mp4 --rights-confirmed --until translate

Note: default Stage 1 requires Demucs model weights. If unavailable, create a copy of config.yaml and disable Demucs ONLY for testing; Stage 2 then transcribes mixed audio and notes that source.

Inspect files:

    python run.py --list-jobs
    ls -lh output/JOB_ID/translate
    cat output/JOB_ID/translate/translation_report.json
    head -30 output/JOB_ID/translate/hindi.srt

Retry failed batches (existing validated batch checkpoints are reused):

    python run.py --resume JOB_ID --until translate

Force translation update without retranscribing English:

    python run.py --resume JOB_ID --force-stage translate --until translate

Config/glossary/model/English transcript changes automatically invalidate a completed translation. No upload or posting occurs.

## Automated tests (no key, no cost)

    python -m unittest discover -s tests -p test_stage3.py -v
    python -m unittest discover -s tests -p test_stage2_improved.py -v
    python -m unittest discover -s tests -p test_pipeline.py -v

A mocked official SDK generates synthetic Hindi responses and tests glossary enforcement, timing limits, JSON-schema calls, cue IDs, retry shortening, batch recovery, saved SRT/JSON and report. Tests cannot establish real LLM quality.

## Upstream verification

The [official OpenAI Python SDK README](https://github.com/openai/openai-python) shows pip install openai, Python >=3.10, env var OPENAI_API_KEY, and client.chat.completions.create. The Python SDK is Apache-2.0; the hosted language model is proprietary. Stage 3 uses the documented Chat Completions API, with strict JSON-schema output. There is no unverified alternative LLM provider.

No live full-video Hindi translation was attempted without a user-authorized API key. A model with this quality may not deliver correct spoken length without voice synthesis; Stage 4 remains pending.

## Saved previous stages

- Stage 1: [process](01_ingest_test_process.md), [measured results](../../reports/stage1/stage1_report.json) — FFmpeg ingestion passed, Demucs separation remains untested.
- Stage 2 chosen Option B: [comparison](02_improved_comparison.md), [metrics](../../reports/stage2/improved_comparison.json) — base.en and optimized English SRT.

Wait for user approval before Stage 4.
