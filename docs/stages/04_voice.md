# Stage 4 — Hindi voice generation and timing

This milestone builds on the approved Stage 2 Option B and revised conversational Stage 3. Stage 1-3 output folders/SQLite data are preserved. **Publishing remains manual**; no automatic upload is implemented.

## Provider verification and limitations

- Official upstream [OpenAI Python SDK](https://github.com/openai/openai-python): Apache-2.0 Python client; `pip install openai`; `client.audio.speech.with_streaming_response.create(model=...,voice=...,input=...,instructions=...,response_format="wav")` with `response.stream_to_file(path)`.
- [Official TTS guide](https://developers.openai.com/api/docs/guides/text-to-speech): `gpt-4o-mini-tts`, built-in voices including `marin`, and **Hindi language support** are documented. Voices are currently **optimized for English**, so Indian Hindi accent/pronunciation must be evaluated with a real paid voice sample.
- This is a hosted proprietary model, independent of ChatGPT's conversation, but requires the user's valid `OPENAI_API_KEY` in local `.env` and may incur charges. Does **not** include voice cloning. Any future cloned voice needs speaker consent and verified rights.
- The built-in `marin` voice is a starting choice; not guaranteed to be the ideal Indian Hindi accent. A better voice/provider can replace this adapter later.

## What Stage 4 adds

Stage 3 provides `translate/hindi_voice_script.json` with natural-Hindi idea blocks, not English sentence-by-sentence subtitles. Stage 4 now:

1. Uses the configured TTS voice for **each complete spoken idea** (reusing any saved per-block WAV checkpoint after a failure).
2. Measures each returned WAV duration, checks the original idea time window and applies a small FFmpeg `atempo` correction only when necessary (default max 1.18x).
3. If a block is too long, **automatically requests a shorter conversational-Hindi rewrite** (default two tries), preserving the original idea, names, numbers and required glossary terms. It then generates and measures speech again. The original Stage 3 script remains unchanged; the version actually spoken is saved as a separate final-script output. If attempts are exhausted or checks fail, the pipeline stops with an actionable error instead of clipping or excessively speeding up speech. This is an independently running API workflow, not an interactive ChatGPT step.
4. Normalizes audio to **24kHz, mono, 16-bit PCM**, places blocks into the **original video timeline** (with silence in source gaps) and writes a complete Hindi speech track.
5. Estimates updated Hindi subtitle timings **inside each actual measured audio block**; this is NOT word-by-word forced alignment. The full alignment and voice/visual mixing are future stages.
6. Records durations, speed adjustments and cache hits; SQLite now migrates existing jobs by adding a pending `voice` stage without disturbing completed Stages 1–3.

## Files

```
output/<job_id>/voice/
  hindi_voice.wav               # final 24kHz mono Hindi narration on original video clock
  voice_report.json             # measured durations, tempo, cache and review warnings
  hindi_tts_estimated.srt       # subtitle cues roughly placed inside measured blocks
  hindi_tts_estimated.json      # estimated alignment source and timing
  hindi_voice_script_final.txt # actual script used for synthesized audio, including rewrites
  hindi_voice_script_final.json # audit of actual spoken idea blocks
  .cache/<fingerprint>/
      0001_tts_raw.wav          # original downloaded TTS audio checkpoint (never public)
      0001_fitted.wav           # normalized and tempo-adjusted speech
```

No MP4, photos, finished video or uploads are produced yet. Source media/voice stays local, not committed to GitHub.

## Run with existing Stage 3 output

On `feature/stage4-hindi-voice-timing`, create `.env` locally (or use existing one) and set **OPENAI_API_KEY** securely. Install Python 3.11, FFmpeg and `pip install -r requirements.txt`.

```bash
python run.py --resume YOUR_JOB_ID --until voice
```

To regenerate voice only, without retranscribing and rewriting:

```bash
python run.py --resume YOUR_JOB_ID --force-stage voice --until voice
```

Stage 4 uses the same job ID, SQLite database and output folder as earlier stages. Changing Stage 3 narration, the TTS model, voice or instructions automatically invalidates Stage 4's prior signature.

For a complete new authorized video (Stage 1 may require Demucs model weights):

```bash
python run.py --file input/owned_video.mp4 --rights-confirmed --until voice
```

Sample `config.yaml` voice settings:

```yaml
voice:
  provider: openai
  model: gpt-4o-mini-tts
  voice: marin
  max_tempo: 1.18
  audio_sample_rate: 24000
  auto_shorten: true
  max_rewrites: 2
  rewrite_model: gpt-4o-mini
```

## Automated tests

```bash
python -m unittest discover -s tests -p 'test_stage4.py' -v
python -m unittest discover -s tests -p 'test_spoken_adapter.py' -v
python -m unittest discover -s tests -p 'test_pipeline.py' -v
```

The synthetic voice tests use **real FFmpeg and PCM wave decoding/assembly** but a mocked TTS service. They verify silence alignment, correct duration, retry/cache, rejects overly long narration, subtitle labeling, fingerprint changes, Stage 3 conversational style checks and SQLite migration.

**Not done:** Real Hindi TTS API call on the user's video, human pronunciation review, independent semantic verification of automatically shortened text, Hindi word forced-alignment, final video rendering, and any publishing. These must be validated before declaring Stage 4 production-ready. When auto-shortening cannot preserve meaning or fit, the job correctly fails rather than silently altering or truncating audio.
