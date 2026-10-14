"""One-shot independent sample of the speaker-authorized local Hindi voice.

No ChatGPT call, translation, eSpeak or social-media publishing.
"""
from __future__ import annotations
import argparse,json,os,sys
from pathlib import Path
# Running as python scripts/preview_personal_voice.py must still locate the repo package.
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from hindi_pipeline.voice_omnivoice import OmniVoiceHindiVoice,reference_files

EXAMPLE = (
    "देखो, सिर्फ ज़्यादा पढ़ना ज़रूरी नहीं है। सही तरीके से पढ़ोगे, "
    "तो चीज़ें जल्दी याद रहेंगी। और यही है इस ट्रिक का असली फायदा।"
)

def main(argv=None):
    p=argparse.ArgumentParser(description="Private personal Hindi voice check")
    p.add_argument("--config",type=Path,default=Path("config.yaml"))
    p.add_argument("--output",type=Path,default=Path("output/private_voice_test.wav"))
    p.add_argument("--text",default=EXAMPLE)
    args=p.parse_args(argv)
    try:
        import yaml
    except ImportError as exc:
        raise RuntimeError("Install project requirements (PyYAML is needed)") from exc
    settings=yaml.safe_load(args.config.read_text(encoding="utf-8")).get("voice",{})
    if settings.get("provider")!="omnivoice":
        raise ValueError("Set voice.provider: omnivoice in config.yaml")
    reference_files(settings)
    if not args.text or len(args.text)>2500:
        raise ValueError("--text must contain 1–2500 characters")
    output=args.output.expanduser().resolve()
    output.parent.mkdir(parents=True,exist_ok=True)
    local=OmniVoiceHindiVoice()
    local.settings=settings
    local.reference_audio=Path(settings["reference_audio"]).expanduser()
    local.reference_transcript=Path(settings["reference_text_file"]).expanduser().read_text(encoding="utf-8").strip()
    temp=output.with_suffix(".temporary.wav")
    try:
        local._synthesize(args.text,temp,settings["model"],
                          settings.get("voice","personal_hindi_reference"),"")
        os.replace(temp,output)
    finally:
        temp.unlink(missing_ok=True)
    import wave
    with wave.open(str(output),"rb") as w:
        length=w.getnframes()/w.getframerate()
    print(json.dumps({
        "provider":"OmniVoice local cloning",
        "sample_path":str(output),"duration_s":round(length,3),
        "review_required":"Listen for naturalness, pronunciation and voice similarity. No upload performed.",
    },ensure_ascii=False,indent=2))

if __name__=="__main__":
    main()
