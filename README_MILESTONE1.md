# English Video → Hindi Video: Milestone 1

**Scope: stages 1–3 only. Nothing uploads to YouTube or Instagram. The existing storyboard renderer on main remains separate.**

## Structure

```
hindi_pipeline/
  common.py        # provider interface, JSON logging, FFmpeg subprocess, SRT writer
  db.py            # SQLite jobs + stage_runs (one row per job/stage)
  ingest.py        # authorized local or yt-dlp video → FFmpeg WAV → Demucs stems
  transcribe.py    # faster-whisper English JSON/SRT with word timestamps
  translate.py     # OpenAI Chat Completions structured Hindi SRT/JSON
  orchestrator.py  # resumable stages and downstream invalidation
run.py             # CLI entry point
config.yaml        # stage config + glossary
.env.example       # example env keys only
requirements.txt   # Python stage 1–3 dependencies
requirements-demucs.txt
Dockerfile
tests/test_pipeline.py
.github/workflows/milestone1.yml
```

Artifacts are saved to `output/<job_id>/ingest`, `output/<job_id>/transcribe`, and `output/<job_id>/translate`. Output includes source video, extracted audio and optional Demucs stems, word timestamp JSON, English SRT and Hindi SRT. The final 16:9/9:16 video, thumbnail, Hindi audio, QC report, and metadata.txt are **future milestones**.

## Install (Linux CPU, Python 3.11)

```bash
sudo apt-get update && sudo apt-get install -y ffmpeg libsndfile1
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m pip install -r requirements-demucs.txt
cp .env.example .env
```

Set `OPENAI_API_KEY` in .env to run Stage 3. The OpenAI translation API may incur charges; this milestone does not promise free LLM inference. Edit `translation.model` (example model: `gpt-4o-mini`) and `translation.glossary` in config.yaml.

**CPU/GPU:** `faster-whisper` defaults to CPU int8 with `small.en`; higher accuracy or faster processing can require a GPU with compatible CUDA and cuDNN, following its README. Demucs is archived, uses PyTorch and can be slow on CPU. It was trained mainly for music, so isolated speech may have artifacts. For a *smoke test only*, set `demucs.enabled: false` in config.yaml; this bypasses separation and processes original audio instead. First use may download large model weights. For a CUDA Docker runtime, build a separate GPU image with matching PyTorch and CTranslate2 libraries.

## Run and verify each stage

Stage 1, authorized local MP4:
```bash
python run.py --file /path/to/owned.mp4 --rights-confirmed --until ingest
```

Or authorized video URL:
```bash
python run.py --url 'https://example.com/authorized-video' --rights-confirmed --until ingest
```

Check the printed job ID and verify `output/<job_id>/ingest/audio.wav` and, with Demucs enabled, `stems/htdemucs/audio/vocals.wav` and `no_vocals.wav` exist. A URL extractor may fail when a service changes or restricts access; use a local authorized file without bypassing controls.

Stage 2:
```bash
python run.py --resume <job_id> --until transcribe
```

Verify `output/<job_id>/transcribe/english.srt` and `english.json`, including nonempty `words` fields.

Stage 3:
```bash
python run.py --resume <job_id> --until translate
```

Verify `output/<job_id>/translate/hindi.srt` and `hindi.json`. Segment IDs/timing are preserved and the Hindi glossary is included. Actual speech length matching is not guaranteed until stage 4 voice synthesis measures it.

Resume, replay, inspect state:
```bash
python run.py --list-jobs
python run.py --resume <job_id>
python run.py --resume <job_id> --force-stage translate
python run.py --resume <job_id> --force-stage ingest
```

Offline unit tests (no credentials/models required):
```bash
python -m unittest discover -s tests -p test_pipeline.py -v
```

Eight unit tests mock Demucs, faster-whisper and the LLM API, test rights confirmation, resumability, failed-stage recovery, SRT timestamps, translation segment-ID integrity and glossary transport. **Live transcription, Demucs separation quality, and real LLM output require an end-to-end authorized video test.**

Docker CPU baseline:
```bash
docker build -t hindi-m1 .
docker run --rm --env-file .env -v "$PWD/output:/app/output" -v "$PWD/state:/app/state" -v "$PWD/input:/input:ro" hindi-m1 --file /input/owned.mp4 --rights-confirmed --until ingest
```

## Upstream README, install, licenses and language limits

These facts were checked against upstream READMEs and GitHub repository metadata in October 2026. Code/model terms may differ; inspect model licenses before commercial use.

| Upstream | Verified usage | License | Hindi / limitation |
| --- | --- | --- | --- |
| [yt-dlp](https://github.com/yt-dlp/yt-dlp) | `pip install yt-dlp`; `python -m yt_dlp` | Unlicense | Downloads media, language-independent. |
| [Demucs](https://github.com/facebookresearch/demucs) | `pip install demucs`; `python -m demucs --two-stems=vocals` | MIT | Separates sound without language awareness; upstream repo archived. |
| [faster-whisper](https://github.com/SYSTRAN/faster-whisper) | `pip install faster-whisper`; word_timestamps=True | MIT | Multilingual Whisper ASR, explicitly transcribing English in this milestone. |
| [OpenAI Python SDK](https://github.com/openai/openai-python) | `pip install openai`, Chat Completions JSON-schema response | Apache-2.0 SDK; hosted model proprietary | Hindi output depends on selected model, quotas and account billing. |
| [OmniVoice](https://github.com/k2-fsa/OmniVoice) | `pip install omnivoice` in README | Apache-2.0 code | Hindi is explicitly listed as code `hi` in `docs/languages.md`; model license and cloned-voice consent still need review before Stage 4. |
| [VoiceStudio](https://github.com/debpalash/VoiceStudio) | Desktop install, not an assumed Python API | AGPL-3.0 | Claims 646-language dubbing; engine must be tested for Hindi. |
| [stickman-video-director](https://github.com/kaomei/stickman-video-director) | Coding-agent skill install | MIT | Storyboard and prompt generator only, not a video-rendering API. |
| [OpenMontage](https://github.com/dydact/openmontage) | Python dependencies plus Remotion/npm | AGPL-3.0 | Agentic production framework; no verified Hindi guarantees. AGPL requirements matter. |
| [Duix-Avatar](https://github.com/duixcom/Duix-Avatar) | Windows-focused setup | Custom DUIX.COM Community License; not a standard OSI license | README lists 8 languages **not including Hindi**. Not selected. |
| [ComfyUI](https://github.com/Comfy-Org/ComfyUI) + [Ref2VA-VSA](https://github.com/Kablex/ComfyUI-Ref2VA-VSA) | GPU custom-node stack, later milestone | Must verify component weights and licenses | ComfyUI uses GPL-3.0; Ref2VA-VSA code includes Apache-2.0 LICENSE. Model weights may carry separate terms. 24 GB RTX 4090 is a reference benchmark, not a universal minimum. |

No speculative plugin/API for the later video stages is included in the runnable code. Stages 4–10 will be proposed only after your approval of this milestone.
