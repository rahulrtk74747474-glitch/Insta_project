# Project checkpoint — saved stages 1–5

This file records the development state after the user's instruction to save all previous stages and move to the next milestone.

## GitHub preservation

- **Main:** [Insta_project/main](https://github.com/rahulrtk74747474-glitch/Insta_project/tree/main) contains the historical initial pipeline, selected Stage 2 Option B, and Stages 3–4 merged in the following order:
  - [PR #5](https://github.com/rahulrtk74747474-glitch/Insta_project/pull/5): structured English → Hindi translation and batch checkpointing — merged.
  - [PR #6](https://github.com/rahulrtk74747474-glitch/Insta_project/pull/6): **preferred natural everyday spoken Hindi** grouped by ideas, separate narration script and subtitle file — merged.
  - [PR #7](https://github.com/rahulrtk74747474-glitch/Insta_project/pull/7): Hindi TTS, time fit, automatic shorter-script retries — merged.
- **Stage 5 in review:** [PR #8](https://github.com/rahulrtk74747474-glitch/Insta_project/pull/8) on `feature/stage5-video-composition` is deliberately **not merged** until the user approves the rendered-video milestone.

## Milestone boundaries and evidence

| Stage | Output | State |
|---|---|---|
| 1 — ingest | source MP4, PCM audio, optional Demucs `vocals.wav` / `no_vocals.wav` | FFmpeg and SQLite recovery verified on user MP4; **Demucs stem separation blocked** (model weights unavailable) |
| 2 — transcription | `english.json`, `english.srt`, `asr_report.json` | Approved **Option B** (`base.en` plus caption optimization), previously tested on user's video |
| 3 — spoken-Hindi adaptation | `hindi_voice_script.json`, `hindi_voice_script.txt`, estimated Hindi SRT | Conversational **tum** style chosen; **live Hindi LLM result not yet validated** (requires configured API key) |
| 4 — Hindi TTS | `hindi_voice.wav`, final-script record, estimated retimed subtitles, voice report | Synthetic wave + FFmpeg tests passed; **live Hindi API voice/pronunciation not verified** |
| 5 — rendering | `hindi_landscape.mp4`, `hindi_portrait.mp4`, render report | Synthetic input produced both formats, full audio-video streams, H.264/AAC, subtitle handling and English audio isolation. Real source-video dub not yet rendered |

## Automated tests

Latest Stage 5 test run: [GitHub Actions 38532680898](https://github.com/rahulrtk74747474-glitch/Insta_project/actions/runs/38532680898).
- 8 Stage 1 pipeline regression tests
- 7 Stage 2 baseline tests
- 6 Stage 2 improved tests
- 14 Stage 3 baseline tests
- 9 Stage 3 spoken-adapter tests
- 10 Stage 4 mocked TTS + real WAV processing tests
- 8 Stage 5 real FFmpeg, libass and audio isolation tests
- **62/62 passed** (these are not 62 real-video end-to-end tests).

The run contains an artifact `stage5-synthetic-landscape-portrait-previews` with two **synthetic** MP4s and the render report; no user-uploaded video is saved to GitHub.

## Manual publishing guardrail

The new `run.py` workflow creates local files only and does **not** upload to YouTube/Instagram or schedule publishing. Legacy upload adapters in the older reelbot prototype remain outside these staged tasks and scheduled publishing is disabled. User approval and manual publication remain required.

## Next work after Stage 5 approval

Test on the actual video with credentials available in the independent runtime, repair the Demucs blocker or explicitly choose original mixed audio, verify Hindi script meaning/accent and actual subtitles, and improve portrait composition and word-level alignment if needed. Do not declare these concerns solved by the synthetic tests.
