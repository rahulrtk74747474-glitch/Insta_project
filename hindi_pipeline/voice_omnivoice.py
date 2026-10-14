"""Stage 4 optional local Hindi TTS provider using k2-fsa/OmniVoice.

Voice-clone prompts are created from the *speaker-authorized local WAV* and its
exact transcript. Media and voice identity never leave the user's machine in
this provider and MUST NEVER be committed to the repository.

See https://github.com/k2-fsa/OmniVoice#voice-cloning
"""
from __future__ import annotations

import hashlib
import math
from pathlib import Path
import wave

from .voice import OpenAIHindiVoice


def reference_files(settings: dict) -> tuple[Path, Path]:
    """Enforce explicit speaker consent and a short private Hindi prompt."""
    if settings.get("reference_voice_consent_confirmed") is not True:
        raise PermissionError(
            "OmniVoice voice cloning requires reference_voice_consent_confirmed: true "
            "for a recording you own or have the speaker's permission to use"
        )
    wav = settings.get("reference_audio")
    text = settings.get("reference_text_file")
    if not isinstance(wav, str) or not wav.strip():
        raise ValueError("voice.reference_audio must point to your local private WAV")
    if not isinstance(text, str) or not text.strip():
        raise ValueError("voice.reference_text_file must point to the matching local Hindi transcript")
    audio, transcript = Path(wav).expanduser(), Path(text).expanduser()
    if not audio.is_file():
        raise FileNotFoundError(f"OmniVoice reference WAV missing: {audio}")
    if not transcript.is_file():
        raise FileNotFoundError(f"OmniVoice reference transcript missing: {transcript}")
    if audio.stat().st_size > 15_000_000:
        raise ValueError("OmniVoice reference WAV is larger than 15 MB")
    with wave.open(str(audio), "rb") as f:
        if f.getnchannels() != 1 or f.getsampwidth() != 2 or f.getframerate() != 24000:
            raise ValueError("OmniVoice reference must be mono 24kHz 16-bit PCM WAV")
        seconds = f.getnframes() / f.getframerate()
    if not 3 <= seconds <= 10:
        raise ValueError("OmniVoice recommends a reference lasting 3–10 seconds")
    transcript_text = transcript.read_text(encoding="utf-8").strip()
    if len(transcript_text) < 15 or not any('\u0900' <= ch <= '\u097f' for ch in transcript_text):
        raise ValueError("OmniVoice reference transcript must match the spoken Hindi WAV")
    return audio, transcript


def reference_digest(settings: dict) -> str:
    """Invalidate stage caches whenever the user's reference or transcript changes."""
    wav, txt = reference_files(settings)
    h = hashlib.sha256()
    for p in (wav, txt):
        with p.open("rb") as stream:
            while piece := stream.read(1024 * 1024):
                h.update(piece)
    return h.hexdigest()


class OmniVoiceHindiVoice(OpenAIHindiVoice):
    """Reuse Stage 4 normalization, timing, caching and optional LLM rewriting."""

    provider_name = "omnivoice"

    def __init__(self, model_instance=None, rewrite_client=None):
        # Parent self.client is solely for *optional* OpenAI text shortening.
        super().__init__(client=rewrite_client)
        self.omnivoice_model = model_instance
        self.clone_prompt = None
        self.settings = {}
        self.reference_audio = None
        self.reference_transcript = None

    def run(self, context):
        settings = context["config"].get("voice", {})
        if settings.get("provider") != "omnivoice":
            raise ValueError("Set voice.provider: omnivoice for local voice cloning")
        audio, transcript = reference_files(settings)
        self.settings = settings
        self.reference_audio = audio
        self.reference_transcript = transcript.read_text(encoding="utf-8").strip()
        # Base pipeline retains Stage 4 retries, per-idea caching and waveform timing.
        return super().run(context)

    def _load_model(self, model_id: str):
        if self.omnivoice_model is not None:
            return self.omnivoice_model
        try:
            from omnivoice import OmniVoice
            import torch
        except ImportError as exc:
            raise RuntimeError(
                "OmniVoice is not installed. Install PyTorch for your CPU/GPU and "
                "'pip install omnivoice'; see docs/stages/04_omnivoice.md"
            ) from exc
        device = self.settings.get("device", "auto")
        if device == "auto":
            device = "cuda:0" if torch.cuda.is_available() else (
                "mps" if getattr(torch.backends, "mps", None) and
                torch.backends.mps.is_available() else "cpu"
            )
        if not isinstance(device, str) or (
            device != "cpu" and device != "mps" and
            not device.startswith(("cuda:", "xpu:"))
        ):
            raise ValueError("voice.device must be auto/cpu/mps/cuda:N/xpu:N")
        dtype = torch.float16 if device.startswith(("cuda:", "xpu:")) else torch.float32
        self.omnivoice_model = OmniVoice.from_pretrained(model_id, device_map=device, dtype=dtype)
        return self.omnivoice_model

    def _synthesize(self, text, output, model, voice, instructions):
        # No network/API needed after model weights have been downloaded.
        reference_files(self.settings)
        system = self._load_model(model)
        if self.clone_prompt is None:
            self.clone_prompt = system.create_voice_clone_prompt(
                ref_audio=str(self.reference_audio),
                ref_text=self.reference_transcript,
            )
        steps = int(self.settings.get("num_step", 32))
        speed = float(self.settings.get("generation_speed", 1.0))
        if not 8 <= steps <= 64 or not math.isfinite(speed) or not .75 <= speed <= 1.25:
            raise ValueError("voice.num_step must be 8–64; voice.generation_speed must be 0.75–1.25")
        speech = system.generate(text=text, voice_clone_prompt=self.clone_prompt,
                                 num_step=steps, speed=speed)
        if not isinstance(speech, (tuple, list)) or not speech or len(speech[0]) < 1200:
            raise RuntimeError("OmniVoice returned invalid or empty speech samples")
        try:
            import soundfile as sf
        except ImportError as exc:
            raise RuntimeError("Install soundfile to save OmniVoice WAV") from exc
        output.parent.mkdir(parents=True, exist_ok=True)
        sf.write(str(output), speech[0], 24000, subtype="PCM_16")
        if not output.is_file() or output.stat().st_size < 44:
            raise RuntimeError("OmniVoice failed to create the Hindi WAV")
