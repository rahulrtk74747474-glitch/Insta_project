# Stage 2 — original vs improved comparison

The original Stage 2 code remains available in `hindi_pipeline/transcribe.py` and branch `feature/stage2-english-transcription`.

The optional implementation is `hindi_pipeline/transcribe_improved.py` plus `hindi_pipeline/caption_optimizer.py`; set `whisper.provider: improved` in the config to activate it. It does not modify source speech, has no voice translation, and **does not publish anywhere**.

## How to run improved Stage 2

Install the prerequisites documented in `README_MILESTONE1.md`. On Python 3.11 (GPU or CPU), the official faster-whisper Python package is supported. This example chooses CPU/int8, `base.en`; initial run downloads model weights:

```bash
python run.py --file input/owned_video.mp4 --rights-confirmed --until transcribe --config config.stage2_improved.yaml
```

The example config stores files in **separate paths** (`output_improved/` and `state/jobs_improved.sqlite3`) so baseline outputs are not overwritten.

Unit tests for old and new behavior (no pretrained model required):

```bash
python -m unittest discover -s tests -p 'test_stage2.py' -v
python -m unittest discover -s tests -p 'test_stage2_improved.py' -v
python -m unittest discover -s tests -p 'test_pipeline.py' -v
```

## Actual video benchmark

See `reports/stage2/improved_comparison.json`. A real end-to-end English transcription was run on the user-uploaded study video with `base.en`, then word-level caption optimization. The new captions have two lines when needed, avoid excessive flashes, and do not drop words. 3 zero-duration word timestamps were marked as estimates. The earlier `tiny.en` run had 741 words and 120 cues, with 11 cues shorter than 0.8s; the improved run recognized 747 words and produced 72 cues, with zero sub-0.8s captions.

Word error rate is **not measured**: 747 words vs 741 does not imply higher accuracy. User must compare transcript wording and speaker's actual audio. The sample media and full transcript were deliberately kept out of this public repository; downloadable local artifacts were prepared separately.

## Comparison choice

- Keep baseline: `whisper.provider` unset or `original`, use `tiny.en` or preferred model.
- Keep improved: `whisper.provider: improved` with `model: base.en`.
- Choose mixed: enable the improved provider but set `model: tiny.en` if you prefer lower CPU and model size. Improved captions can work with any supported faster-whisper model.

Important: The earlier Demucs step could not fetch model weights. We intentionally used mixed audio in **both** actual-video comparisons and labelled the condition. This stage is English transcription only; do not confuse it with voice cloning, Hindi generation, or final video assembly.
