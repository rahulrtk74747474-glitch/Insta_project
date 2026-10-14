# Stage 5 — Video assembly and reviewable MP4 exports

Stage 5 is a **local rendering milestone** built on preserved Stages 1–4. It creates **landscape 16:9 and portrait 9:16 Hindi video previews** using the original authorized video, Stage 4 synthesized Hindi voice, and Stage 4's estimated Hindi SRT.

## Independence and manual publishing

The pipeline runs as normal Python + FFmpeg code without a ChatGPT conversation. The previously saved stages still own transcription, conversational Hindi adaptation, TTS, retries and their SQLite records.

**Never auto-publish**: Stage 5 does not call social-media APIs, read publishing tokens or schedule posts. Its only end products are locally saved MP4s and a report. The source English audio stream is deliberately **not** mapped into either video. That is essential to avoid simultaneous English speech under the Hindi dub.

## Outputs

Under `output/<job_id>/render/`:

- `hindi_landscape.mp4` — 16:9, default 1280×720, H.264/AAC.
- `hindi_portrait.mp4` — 9:16, default 720×1280, H.264/AAC.
- `render_report.json` — output dimensions, codecs, duration, background choice, subtitle warning and paths.

The original source is **not changed**. Previous Stage 1–4 artifacts are retained; SQLite automatically adds the pending `render` row to any old job. The Stage 5 provider can be rerun without asking the previous stages to retranscribe or synthesize audio.

## Video framing

For portrait clips, default **fit** rescales the entire original frame with black padding so no visual content is cropped. **fill** crops source edges to fill the portrait frame; cropping may cut off essential on-screen text. Users should inspect the preview before manual posting.

For both formats, optional libass burn-in renders Devanagari subtitles near the lower section of the frame. The Noto Sans Devanagari font is suggested. **These subtitle cue times are estimated within actual measured Hindi TTS idea blocks, not forced word-level alignment**, so check synchrony before publication.

If Demucs was able to create a real `no_vocals.wav` stem, `render.mix_separated_background: true` optionally mixes it quietly beneath the Hindi narration. If the stem is unavailable (as in the previous Stage 1 video test), the renderer **refuses** this option rather than unintentionally mixing the original English speaker back in. Default is Hindi voice only.

## Setup

Linux CPU, Python 3.11, FFmpeg with **libass** support and an installed Devanagari font:

```bash
sudo apt-get update
sudo apt-get install -y ffmpeg fonts-noto-core
pip install -r requirements.txt
```

To check subtitle rendering capability, use `ffmpeg -filters | grep subtitles`. Without libass, set `render.burn_subtitles: false` to make the video only, retaining external SRT for later work.

Stage 1 may require Demucs weights, Stage 2 uses faster-whisper, and Stages 3–4 need configured API credentials for live Hindi generation. **Stage 5 rendering itself does not call an AI API.**

## Run

For an **existing job with saved Stage 4 audio**, no preceding stages need reprocessing:

```bash
python run.py --resume YOUR_JOB_ID --until render
```

To rerender only Stage 5 with new resolution, font or portrait mode:

```bash
python run.py --resume YOUR_JOB_ID --force-stage render --until render
```

Run Stages 1–5 on a new authorized file with all required dependencies and keys:

```bash
python run.py --file input/owned_video.mp4 --rights-confirmed --until render
```

### Config

```yaml
render:
  landscape: [1280, 720]
  portrait: [720, 1280]
  portrait_mode: fit        # fit = no crop; fill = full frame with side crop
  fps: 30
  preset: veryfast
  crf: 23
  burn_subtitles: true
  subtitle_font: Noto Sans Devanagari
  subtitle_font_size: 24
  mix_separated_background: false
  background_volume: 0.12
```

## Test evidence and limitations

Automated CI exercises actual FFmpeg + libass rendering of a synthetic 3.2-second H.264 source with original 220 Hz English stand-in audio, plus a separate 440 Hz WAV representing Hindi TTS. The test checks **both aspect ratios**, video duration, codec mapping, subtitle burn-in path, and that the rendered audio is dominated by the Hindi track rather than retaining the original source tone. It also verifies refusal of a missing separated background stem and missing subtitles.

These tests are **not** a human assessment of the 4:53 user's original video or a real Hindi voice. Previously unresolved: Demucs model availability, real natural Hindi translation, TTS accent and timing quality. Neither AI-generated illustrations, advanced crop tracking, speech-word forced alignment, automatic thumbnails, human moderation nor automatic publishing are included here.

Inspect exported MP4s manually before approving this milestone. Stage 5 does not publish.
