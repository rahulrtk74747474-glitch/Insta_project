---
name: hindi-reel-production
description: Plan and render original Hindi storyboard-based educational Reels with licensed source material and safe publishing gates.
---

# Hindi Reel Production

1. Require explicit source rights before publication. Do not bypass a site's access controls.
2. Extract or provide accurate source transcript, then write a genuinely original Hindi narration.
3. Create `data/storyboards/<slug>.json` with visual directions and timing for 4–8 second shots.
4. Retain consistent character design, colorful pencil/marker linework, typography and 9:16 composition.
5. Generate or supply an original scene keyframe for each shot, render clips, and concatenate with temporary or user-provided narration.
6. Test output locally using `python -m reelbot --storyboard data/storyboards/time_loop.json --output dist/demo.mp4`.
7. Never publish without explicit confirmation of rights and OAuth/API configuration.

This is an **instruction skill for coding agents**, not a text-to-video engine. The Vercel `npx skills` CLI may discover/install it, but actual rendering requires Python and FFmpeg.
