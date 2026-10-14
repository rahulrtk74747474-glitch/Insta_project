# Insta Project — Hindi Doodle Reel Automation

**MVP stage: code and workflow are under review. Nothing is auto-posting yet.**

## What works (once CI passes)

The renderer converts a Hindi storyboard to an original 9:16 (720×1280, 30fps) colored doodle video, with a Hindi temporary narration and editable scene durations. You can provide your own WAV/MP3 narration using `--voice`. Visual asset overrides (`image` on a scene, relative to its storyboard file) let us replace placeholder doodles with professionally generated original drawings. The seven-scene study example is in `data/storyboards/time_loop.json`.

The pipeline also includes:
- GitHub Actions PR/push tests and a downloadable MP4 preview artifact.
- Permission-checked JSON queue and upload-ID tracking so retries can skip already published platforms.
- Upload code for the official YouTube Data API and Instagram Reels resumable upload API (live publishing **not tested**).

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

## Daily publishing at 7 PM IST

`.github/workflows/reel.yml` contains a GitHub Actions schedule for **6:35 PM IST**. If enabled and merged into the default branch, it prepares an approved queued Reel and waits until 7:00 PM IST before making API publication requests. GitHub schedule starts can be delayed, and actual Instagram availability may occur later because video processing is asynchronous. A self-hosted runner offers more predictable scheduling.

Required repository settings under **Settings → Secrets and variables → Actions**:

| Kind | Key | Notes |
| --- | --- | --- |
| Variable | `ENABLE_AUTOPUBLISH` | Set `true` only after fully testing and confirming permissions |
| Variable | `YOUTUBE_PRIVACY` | `private` for testing; `public` only after verified |
| Secret | `YOUTUBE_CLIENT_ID` | OAuth client |
| Secret | `YOUTUBE_CLIENT_SECRET` | OAuth secret |
| Secret | `YOUTUBE_REFRESH_TOKEN` | User-authorized offline refresh token |
| Secret | `META_IG_USER_ID` | Professional Instagram account ID |
| Secret | `META_ACCESS_TOKEN` | Access token with publishing privileges |

The scheduled workflow runs only on **main** after a merge, not on a PR branch. Real publishing must remain disabled until both API adapters are tested with your connected accounts. YouTube's own docs disagree on whether unverified projects can publish videos publicly; test your credentials before assuming public visibility. Instagram needs an eligible professional account and permissioned Meta app; no paid hosting is necessary for local resumable uploads.

The job saves successful platform upload IDs in queue state and makes a GitHub commit, even when a second platform upload fails.

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
