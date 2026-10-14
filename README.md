# Insta Project — Hindi Doodle Reel Automation

> **Current project policy (Milestone 1): manual publication only.** Scheduled Instagram/YouTube publishing has been disabled in `.github/workflows/reel.yml`. The new `run.py` pipeline only creates local artifacts. See [README_MILESTONE1.md](README_MILESTONE1.md) for setup and tests.


**Stage 2 selection: Option B (`base.en` + improved caption optimizer), chosen by user. Nothing auto-posts.**

The default English ASR provider is now `ImprovedFasterWhisper`. See [Stage 2 comparison and configuration](docs/stages/02_improved_comparison.md). Set `whisper.provider: original` to use legacy caption formatting.

## Stage 3 — Hindi translation (in development, review branch)

English Stage 2 (Option B `base.en`) and Stage 1 are preserved. Stage 3 produces only `hindi.srt`, `hindi.json`, and `translation_report.json`, with a resumable per-batch cache. No video is rendered or uploaded; real API integration requires a key in `.env`. See [Stage 3 instructions](docs/stages/03_translate.md).

## What works (once CI passes)

The renderer converts a Hindi storyboard to an original 9:16 (720×1280, 30fps) colored doodle video, with a Hindi temporary narration and editable scene durations. You can provide your own WAV/MP3 narration using `--voice`. Visual asset overrides (`image` on a scene, relative to its storyboard file) let us replace placeholder doodles with professionally generated original drawings. The seven-scene study example is in `data/storyboards/time_loop.json`.

The pipeline also includes:
- GitHub Actions PR/push tests and a downloadable MP4 preview artifact.
- Permission-checked JSON queue and upload-ID tracking so retries can skip already published platforms.
- Historical platform upload adapters exist in the older reelbot prototype but are not used by this pipeline; publishing is disabled.

## Run a no-cost prototype locally

Requires Python 3.11+, FFmpeg, eSpeak, Noto Devanagari fonts.

```bash
sudo apt-get install ffmpeg espeak fonts-noto-core
pip install -r requirements.txt
python -m unittest discover -s tests -v
python -m reelbot --storyboard data/storyboards/time_loop.json --output dist/reel.mp4
```

Your replacement voice can be supplied at render time:

```bash
python -m reelbot --storyboard data/storyboards/time_loop.json --voice path/to/voice.wav --output dist/reel.mp4
```

This is a basic colored-animation prototype. The next major improvement is generating high-detail original scene drawings and moving individual elements, rather than only progressive scene reveals.

## Link queue

`data/queue.json` holds the incoming sources and production state. New items must include a valid storyboard file and `rights_confirmed: true` before publication. The supplied Instagram example has `rights_confirmed: false` because permission to republish was not established.

Example authorized item:
```json
{
  "id": "episode-002",
  "source_url": "https://example.com/authorized-source",
  "rights_confirmed": true,
  "status": "queued",
  "storyboard": "data/storyboards/episode-002.json",
  "title": "Hindi Study Tip",
  "description": "A new, original Hindi study explainer",
  "posted": {}
}
```

Preview the earliest approved queued storyboard without publishing:
```bash
python -m reelbot --queue data/queue.json --output dist/test.mp4
```

**Current limitation:** Input links are stored, but social-link downloading, speech transcription, automatic translation, script validation, automatic original image generation and automated storyboard creation are NOT integrated yet. Link-only unattended production therefore remains a later phase.

## Manual publishing only

The English-to-Hindi pipeline (`run.py`) **creates files and never uploads video or calls social-media publishing APIs**. The legacy reel-preview project contains old publishing adapters for historical reference, but the GitHub Actions scheduled/publish jobs have been disabled. No publishing credentials are required for Stages 1–3. All video outputs are intended for manual review and manual publication.

## Vercel Labs skills check

[vercel-labs/skills](https://github.com/vercel-labs/skills) is a legitimate open-source CLI for installing *AI coding-agent instruction skills*. It does **not** provide video generation or automatic posting itself. The repository includes `.agents/skills/hindi-reel-production/SKILL.md`; compatible agents may install it with:

```bash
npx skills add ./.agents/skills/hindi-reel-production -a codex -y
```

Verified in GitHub Actions: `npx skills --help` ran successfully and `npx skills add ./.agents/skills/hindi-reel-production --list` found the `hindi-reel-production` skill. This confirms **skill discovery**, not automatic video generation.

## Next development stages

1. Source access with explicit rights / permissions, local media transcription (Faster-Whisper).
2. Offline Hindi translation and robust original script/storyboard generation.
3. Consistent original illustration assets, shot animation, accurate captions and better Hindi narration.
4. API integration tests and handling for expired tokens, retries, errors and publication status.

Official source references: [Meta's Reels Publishing Sample](https://github.com/fbsamples/reels_publishing_apis/tree/main/insta_reels_publishing_api_sample), [YouTube videos.insert](https://developers.google.com/youtube/v3/docs/videos/insert), [GitHub Actions](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax).
