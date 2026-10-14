# Stage 4: Personal Hindi Voice Cloning with OmniVoice

## Why this change

The 14.8-second review videos previously used eSpeak, **not OmniVoice**. That robotic voice was only a temporary layout/timing test, not a true quality demonstration. This feature directly integrates [k2-fsa/OmniVoice](https://github.com/k2-fsa/OmniVoice) as the first-choice local Stage 4 Hindi TTS source. The resulting speech is used by *both* Stage 5 landscape/portrait outputs.

**No actual cloned voice has yet been generated.** The development environment has no OmniVoice weights, no GPU and could not reach Hugging Face. Tests use fake model responses and synthetic WAVs; real accent, identity similarity and pronunciation require listening to an actual generated sample.

## What OmniVoice actually supports

The official README specifies a Python API for voice cloning from a short reference WAV with an exact transcript. It recommends **3–10 seconds** of same-language reference audio and says voice cloning is its most stable mode. Hindi appears explicitly in its supported language list (ISO code hi).

- Model: k2-fsa/OmniVoice, loaded through OmniVoice.from_pretrained
- Clone prompt: create_voice_clone_prompt(ref_audio=..., ref_text=...), constructed **once** for the full video.
- Speech: model.generate(text=..., voice_clone_prompt=..., num_step=32, speed=1.0), returning 24 kHz samples.
- WAV: soundfile writes 24 kHz mono PCM, fed into the existing Stage 4 caching, tempo fitting and timeline composer.

VoiceStudio (debpalash/VoiceStudio) was also evaluated and now offers a local API and an OmniVoice backend. It is not silently substituted if OmniVoice fails.

## Reference kit, privacy and setup

The user provided their own ~64-second voice recording. We prepared a lightly filtered 9.2-second excerpt and a matching editable Hindi transcript. The reference audio/text are *private* and are NOT committed to the public GitHub repository.

1. Download the separate private OmniVoice Reference Kit shared in the ChatGPT conversation.
2. Verify the text transcript against the actual 9.2 seconds of speech. Correct misheard/missing words before cloning.
3. Copy the WAV and TXT to input/private_voice/ in your *local* checkout. This directory is gitignored.
4. Install Python 3.11, FFmpeg, PyTorch compatible with your hardware, the project's requirements, and the published OmniVoice package.

    python -m pip install -r requirements.txt
    python -m pip install omnivoice soundfile

The first model load must download weights from Hugging Face. Use a machine with enough RAM/VRAM and Internet connectivity. CUDA is preferred, but the adapter supports CPU for testing; CPU may be very slow or exhaust memory. Confirm the OmniVoice model-weight licence separately before commercial deployment.

## Example config.yaml

    voice:
      provider: omnivoice
      model: k2-fsa/OmniVoice
      voice: personal_hindi_reference
      reference_voice_consent_confirmed: true
      reference_audio: input/private_voice/hindi_voice_reference_9s.wav
      reference_text_file: input/private_voice/hindi_voice_reference_9s.txt
      device: auto
      num_step: 32
      generation_speed: 1.0
      max_tempo: 1.18
      audio_sample_rate: 24000
      auto_shorten: true
      max_rewrites: 2
      rewrite_model: gpt-4o-mini

Set the reference consent field true **only** for your own voice or with express speaker permission. The transcript is required, and the 3–10-second sample is validated. Reference WAV and transcript bytes affect the fingerprint; changing either forces regeneration, so stale voices are not reused.

## First proper REAL voice check — no English ASR/ChatGPT required

Run this command independently on your voice-capable computer:

    python scripts/preview_personal_voice.py --config config.yaml --output output/private_voice_test.wav

It speaks a *new* Hindi passage, different from the supplied reference, so you can check whether the model really reproduces the speaker's voice instead of replaying a clip. Review pronunciation, Hinglish words, speaker similarity, natural pacing and background hiss. Do not advance to full-video generation if the quality is unacceptable.

## Full video and both formats

After the prior Stage 3 output exists, run:

    python run.py --resume YOUR_JOB_ID --force-stage voice --until render

This invokes Stage 4's local OmniVoice cloning, existing measured TTS timing/retries, then Stage 5's landscape and portrait H.264/AAC video exports, all in the standalone Python automation. No social-media uploads occur.

Automatic *text shortening* is still configured to use a separate OpenAI language-model API when an idea exceeds its time budget. This is independent of the ChatGPT conversation and requires OPENAI_API_KEY. To avoid all remote language-model calls within Stage 4, set auto_shorten: false; overly long blocks then fail safely rather than being forced or clipped.

Older OpenAI TTS remains available by explicitly setting provider: openai, model: gpt-4o-mini-tts and voice: marin. eSpeak is not a fallback in the Stage 4 production code.

## Verification

The dedicated GitHub workflow installs FFmpeg and runs mocked-model tests for reference validation, consent, prompt reuse, cache invalidation, output duration, and provider selection, along with Stage 4 regression tests. Neither the real private recording nor actual voice-clone weights are uploaded to CI. An offline unit-test pass must never be described as proof of authentic voice cloning quality.
