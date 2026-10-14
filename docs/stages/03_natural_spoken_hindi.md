# Stage 3 — Natural, everyday spoken Hindi (Option: spoken_adaptation)

This is a user-requested revision of Stage 3. **The English transcript is an input for rewriting, not the narration to read aloud.** Stages 1 and 2 Option B remain unchanged.

## How it works

1. Stage 2 supplies English time-stamped subtitles (base.en and optimized captions).
2. `idea_blocks()` groups related English captions into complete thoughts (defaults: 6–14 seconds, up to 4 English cues per idea; split at pauses and sentence boundaries).
3. An OpenAI structured-output provider **adapts ideas into day-to-day Hindi**, using consistent informal 'tum' pronouns, ordinary Devanagari/Hinglish words such as 'एग्जाम', 'दिमाग', 'ट्रिक', and natural bridges. It must preserve facts, named people, numbers, examples and negations.
4. The script is checked for order, Hindi text, glossary terms and approximate speaking duration. Invalid batches are retried up to 3 times and saved to a resume cache keyed on the input and style configuration.
5. `hindi_voice_script.json` and `hindi_voice_script.txt` contain the **canonical narration script** for future TTS, rather than fragments copied from the subtitles.
6. A **separate** `hindi.srt` and `hindi.json` are generated from that Hindi narration. Initial subtitle timing is estimated proportionally within each idea block. **Audio timing is NOT verified until Stage 4 synthesizes the Hindi voice.**

## Files

```
output/<job_id>/translate/
  hindi_voice_script.txt        # Natural, continuous speech; the source for future TTS
  hindi_voice_script.json       # Idea blocks + original cue mapping + duration estimates
  hindi.srt                     # Hindi subtitles derived from the new Hindi script
  hindi.json                    # Approximate subtitle timings and source block references
  translation_report.json       # Output metrics, warnings, checkpoints used
  .staging/<fingerprint>/spoken_*.json  # Private resumable caches
```

Nothing is uploaded or published by the pipeline. The video itself and scripts stay local, outside the public GitHub repository.

## Style example (editorial illustration, not an API output)

English: “Imagine you sit down for your exam, and everything just clicks.”

A literal caption: “सोचिए, परीक्षा में बैठे हैं और सब कुछ आसानी से याद आ रहा है।”

Natural spoken script: “सोचो, एग्जाम देने बैठे हो और जो भी पढ़ा था, सब फटाफट याद आ रहा है।”

This adapts the explanation, not the factual content. Avoid adding unsupported neuroscience claims, techniques or new examples.

## Run / switch mode

In `config.yaml`:

```yaml
translation:
  provider: openai
  mode: spoken_adaptation
  audience: tum
  min_group_seconds: 6
  max_group_seconds: 14
  max_group_cues: 4
  model: gpt-4o-mini
  batch_size: 4
  max_quality_attempts: 3
  speed_tolerance: 1.15
```

Set `OPENAI_API_KEY` in local `.env` only (never in source code or GitHub). OpenAI API use may incur charges.

```bash
python run.py --resume <job_id> --until translate
python run.py --resume <job_id> --force-stage translate --until translate
python -m unittest discover -s tests -p 'test_spoken_adapter.py' -v
```

To revert to the original one-to-one caption translation (retained for comparison), set `translation.mode: subtitle_literal`. Changing the style/settings invalidates Stage 3's old fingerprint and regenerates it, without retranscribing English.

## Tests and limitations

Unit tests mock the LLM and verify grouping, separate narration/captions, no missing English cues, glossary enforcement, shorter retries, SQLite provider switching, checkpoint recovery and estimated alignment disclosure. Real LLM language quality must be reviewed on an authorized example video.

**Stage 4 must synthesize and time-fit Hindi voice and then replace estimated subtitle timings with actual speech timings.** The system does not create audio files in Stage 3.
