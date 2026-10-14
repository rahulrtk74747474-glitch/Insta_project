# Stage 6 — Finished Hindi video review

Status: review-only, not published.

Source: the user's authorized Time Loop video, kept local. The new Hindi script is a conversational educational adaptation, not literal English transcript translation. OmniVoice was skipped, eSpeak was not used. Voice is generic male Hindi neural TTS (hi-IN-MadhurNeural), NOT a clone of the user's recording.

Verified local exports: portrait 720×1280 and landscape 1280×720, both H.264/AAC and 344.064 seconds (5:44). Original source was 293.481 seconds; visuals were slowed to 1.1724× duration, preserving unaccelerated Hindi voice. Original English audio was not included. Rendered output peak volume ~-1 dBFS; mean -17.4 dBFS.

The service returned no usable Hindi WordBoundary timestamps, so subtitle times are APPROXIMATED from script character lengths. They must be reviewed for sync before publishing.

Standalone voice synthesis, independent of the interactive ChatGPT session:

    python scripts/edge_hindi_tts.py --output dist/natural_hindi_voice.mp3

Standalone local video render, given an authorized source MP4 and generated speech:

    python scripts/render_neural_hindi.py --source /path/to/authorized-original.mp4 --voice dist/natural_hindi_voice.mp3 --subtitles dist/natural_hindi_voice.srt --output-dir dist/final_review

Dependencies: project requirements including Pillow; edge-tts; FFmpeg with libass; Noto Sans Devanagari fonts. Internet access needed for the unofficial Edge TTS speech endpoint, subject to availability and Microsoft service terms. Confirm suitability and rights before commercial use.

Stage 4 generic pipeline can now select provider edge, model edge-neural, voice hi-IN-MadhurNeural, and rate '-2%'. Stage 3 automatic Hindi translation still requires a configured LLM API. The prewritten Stage 6 adaptation is an alternative without needing a live translation API at render time.

User media, voice reference, generated voice and MP4s were NOT committed to public GitHub. Automatic publishing stays disabled.

Known limitations: subtitle sync estimated; voice naturalness needs subjective review; scene-to-narration matching approximate due to ~17% stretched visuals; no auto-upload. Full end-to-end performance can be improved with Hindi forced alignment and review.
