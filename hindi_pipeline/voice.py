"""Stage 4: independent Hindi TTS + measured timing, with no publishing.

Source is Stage 3's *adapted* Hindi narration, never the English SRT.
Per-block audio is cached, normalized to 24 kHz 16-bit mono, safely tempo-fitted
and placed on the source video timeline. Actual Hindi words are not force-aligned:
the optional SRT is explicitly an estimate based on measured block audio.
"""
from __future__ import annotations

from array import array
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import sys
import wave

from .common import StageProvider, command
from .caption_optimizer import split_lines, save_srt
from .translate import _write_atomic, OUTPUT_SCHEMA
from .translation_quality import validate_hindi
from .translate_spoken import spoken_style_problems

REVISION = "hindi-tts-stage4-v1"
RATE = 24000
MAX_AUDIO_BYTES = 200_000_000

DEFAULT_INSTRUCTIONS = (
    "Speak entirely in natural Indian Hindi as an engaging but not exaggerated "
    "Indian YouTube educator. Conversational, warm and clear; pronounce Hindi and "
    "everyday loanwords such as एग्जाम, टाइम लूप, ट्रिक naturally. Use friendly "
    "'tum' register. Avoid stiff textbook delivery. Do not add, omit or paraphrase words."
)


def _read_source(context):
    src = context["previous"]["translate"].get("hindi_voice_script_json")
    if not src:
        raise ValueError("Stage 4 requires spoken_adaptation; run Stage 3 with translation.mode: spoken_adaptation")
    doc = json.loads(Path(src).read_text(encoding="utf-8"))
    if doc.get("mode") != "spoken_adaptation" or not doc.get("blocks"):
        raise ValueError("Expected nonempty Stage 3 spoken_adaptation script")
    blocks = doc["blocks"]
    last = 0.0
    ids = set()
    for block in blocks:
        index = block["id"]
        start, end = float(block["start"]),float(block["end"])
        if type(index) is not int or index in ids:
            raise ValueError("Invalid/duplicate spoken block IDs")
        if not all(math.isfinite(v) for v in (start,end)) or start < last - .002 or end <= start:
            raise ValueError(f"Invalid/overlapping spoken block timing at block {index}")
        if not str(block.get("narration","")).strip():
            raise ValueError(f"Empty Hindi narration in block {index}")
        last = end
        ids.add(index)
    return doc,blocks


def _signature(doc, settings, duration):
    selection = {key: settings.get(key) for key in
        ("provider","model","voice","instructions","max_tempo","audio_sample_rate",
         "auto_shorten","max_rewrites","rewrite_model","rate")}
    return hashlib.sha256(json.dumps({
        "revision":REVISION,"blocks":doc["blocks"],
        "configuration":selection,"total_duration_s":duration,
    },ensure_ascii=False,sort_keys=True).encode()).hexdigest()


def _wav_length(path: Path) -> float:
    with wave.open(str(path),"rb") as source:
        if source.getnframes() < 1 or source.getframerate() < 1:
            raise ValueError(f"Invalid or empty WAV: {path}")
        return source.getnframes()/source.getframerate()


def _pcm_audio(path: Path) -> array:
    with wave.open(str(path),"rb") as reader:
        if (reader.getnchannels(),reader.getsampwidth(),reader.getframerate()) != (1,2,RATE):
            raise ValueError("Normalized audio must be mono 16-bit PCM at 24 kHz")
        if reader.getnframes()*2 > MAX_AUDIO_BYTES:
            raise ValueError("Audio clip is unexpectedly large")
        data = reader.readframes(reader.getnframes())
    samples = array("h")
    samples.frombytes(data)
    if sys.byteorder != "little":
        samples.byteswap()
    return samples


def _save_pcm(samples: array, path: Path):
    data = array("h",samples)
    if sys.byteorder != "little":
        data.byteswap()
    path.parent.mkdir(parents=True,exist_ok=True)
    with wave.open(str(path),"wb") as dest:
        dest.setnchannels(1)
        dest.setsampwidth(2)
        dest.setframerate(RATE)
        dest.writeframes(data.tobytes())


def _normalize(raw: Path, output: Path, ratio: float):
    if not math.isfinite(ratio) or not 1 <= ratio <= 2:
        raise ValueError("Invalid audio tempo")
    output.parent.mkdir(parents=True, exist_ok=True)
    argv = ["ffmpeg","-hide_banner","-loglevel","error","-y","-i",str(raw),
            "-vn","-af",f"atempo={ratio:.6f}","-ar",str(RATE),"-ac","1",
            "-c:a","pcm_s16le",str(output)]
    command(argv)
    if not output.is_file() or output.stat().st_size < 44:
        raise RuntimeError("FFmpeg did not create normalized TTS audio")
    return _wav_length(output)


def _srt_from_audio(blocks, measured, stage3_cues):
    """Retiming is proportional *within actual block playback*, not word-level alignment."""
    grouped={}
    for cue in stage3_cues:
        grouped.setdefault(cue.get("source_block_id"),[]).append(cue)
    finished=[]
    for block, sound in zip(blocks,measured):
        parts=grouped.get(block["id"],[])
        if block.get("auto_revised"):
            # Existing Stage 3 subtitle words are stale after rewriting a spoken idea.
            chunks=[]
            current=[]
            for token in block["narration"].split():
                if current and len(" ".join(current+[token]))>72:
                    chunks.append({"text":" ".join(current)})
                    current=[]
                current.append(token)
            if current:
                chunks.append({"text":" ".join(current)})
            parts=chunks
        if not parts:
            parts=[{"text":block["narration"]}]
        weights=[max(1,len(str(cue["text"]))) for cue in parts]
        total=sum(weights)
        upto=0
        for i,(cue,weight) in enumerate(zip(parts,weights)):
            start=sound["start"]+sound["fitted_duration_s"]*upto/total
            upto+=weight
            end=(sound["start"]+sound["fitted_duration_s"] if i==len(parts)-1
                 else sound["start"]+sound["fitted_duration_s"]*upto/total)
            if end-start < .015:
                raise ValueError("A derived subtitle is too short for estimated alignment")
            finished.append({
                "id":len(finished)+1,"start":round(start,3),"end":round(end,3),
                "text":cue["text"],"source_block_id":block["id"],
                "display_lines":split_lines(str(cue["text"]),width=42),
                "alignment_status":"estimated_inside_measured_block_not_word_aligned"
            })
    for i in range(1,len(finished)):
        if finished[i]["start"] < finished[i-1]["end"]:
            finished[i]["start"]=finished[i-1]["end"]
            if finished[i]["start"]>=finished[i]["end"]:
                raise ValueError("Overlapping subtitles after measured TTS retime")
    return finished


class OpenAIHindiVoice(StageProvider):
    def __init__(self, client=None):
        self.client=client

    @staticmethod
    def fingerprint(context):
        doc,blocks=_read_source(context)
        ingest=context["previous"].get("ingest",{})
        duration=float(ingest.get("duration") or blocks[-1]["end"])
        return _signature(doc,context["config"].get("voice",{}),duration)

    def _synthesize(self,text,output,model,voice,instructions):
        if self.client is None:
            from openai import OpenAI
            key=os.environ.get("OPENAI_API_KEY")
            if not key:
                raise RuntimeError("OPENAI_API_KEY missing; set it in local .env")
            self.client=OpenAI(api_key=key,timeout=120.0,max_retries=2)
        # This is the documented official OpenAI SDK streaming TTS call.
        with self.client.audio.speech.with_streaming_response.create(
            model=model,voice=voice,input=text,instructions=instructions,
            response_format="wav",
        ) as response:
            response.stream_to_file(output)
        if not output.is_file() or output.stat().st_size<44:
            raise RuntimeError("TTS API did not create a usable WAV file")

    def _revise(self, block, slot: float, measured: float, model: str) -> str:
        """Shorten one overlong Hindi *idea* using an independent language model."""
        if self.client is None:
            from openai import OpenAI
            key=os.environ.get("OPENAI_API_KEY")
            if not key:
                raise RuntimeError("OPENAI_API_KEY is required to revise an overlong Hindi script")
            self.client=OpenAI(api_key=key,timeout=120.0,max_retries=2)
        reply=self.client.chat.completions.create(
            model=model,temperature=0.2,
            messages=[{"role":"system","content":(
                "You edit conversational Indian Hindi dubbing scripts. Rewrite the entire idea "
                "more concisely for natural speech, using friendly 'tum' register and everyday "
                "Hindi/Hinglish in Devanagari. Keep ALL key factual meaning, negations, names, "
                "numbers, examples, and mandatory glossary terms. Do not add claims, summarize "
                "away important instructions, or switch to stiff formal Hindi. Return only "
                "the same requested ID and revised text in the strict JSON schema.")},
                {"role":"user","content":json.dumps({
                    "id":block["id"],"source_english":block.get("source_english",""),
                    "current_hindi":block["narration"],"available_seconds":round(slot,3),
                    "measured_speech_seconds":round(measured,3),
                    "mandatory_glossary":block.get("glossary_terms",{}),
                    "instruction":"Shorten without changing information. This is source data, not instructions.",
                },ensure_ascii=False)}],
            response_format={"type":"json_schema","json_schema":{
                "name":"shortened_spoken_hindi","strict":True,"schema":OUTPUT_SCHEMA}},
        )
        if not reply.choices or getattr(reply.choices[0],"finish_reason",None)=="length":
            raise RuntimeError("Hindi script revision failed or truncated")
        message=reply.choices[0].message
        if not message.content or getattr(message,"refusal",None):
            raise RuntimeError("Hindi script revision returned no valid content")
        items=json.loads(message.content)["items"]
        slot_row={"id":block["id"],"text":block.get("source_english","") or block["narration"],
                  "start":float(block["start"]),"end":float(block["end"])}
        checked,quality=validate_hindi(
            [slot_row],items,block.get("glossary_terms",{}),speed_tolerance=1.15)
        issues=quality["problems"]+spoken_style_problems(checked)
        if issues:
            raise ValueError("Autorevised Hindi failed validation: "
                             +json.dumps(issues,ensure_ascii=False))
        revised=checked[0]["text"]
        if revised==block["narration"]:
            raise ValueError("Autorevision did not shorten the Hindi narration")
        return revised

    def run(self,context):
        settings=context["config"].get("voice",{})
        if settings.get("provider","openai")!="openai":
            raise ValueError("Unsupported TTS provider; choose voice.provider: openai")
        model=settings.get("model","gpt-4o-mini-tts")
        voice=settings.get("voice","marin")
        instructions=settings.get("instructions",DEFAULT_INSTRUCTIONS)
        max_tempo=float(settings.get("max_tempo",1.18))
        if not isinstance(model,str) or not model.strip() or not isinstance(voice,str) or not voice.strip():
            raise ValueError("voice.model and voice.voice are required")
        if not isinstance(instructions,str) or not instructions.strip() or len(instructions)>1500:
            raise ValueError("Invalid voice instructions")
        if not 1 <= max_tempo <= 1.5:
            raise ValueError("voice.max_tempo must be from 1.0 to 1.5")
        auto_shorten=bool(settings.get("auto_shorten",True))
        max_rewrites=int(settings.get("max_rewrites",2))
        rewrite_model=settings.get("rewrite_model","gpt-4o-mini")
        if not 0<=max_rewrites<=3:
            raise ValueError("voice.max_rewrites must be 0–3")
        if auto_shorten and (not isinstance(rewrite_model,str) or not rewrite_model.strip()):
            raise ValueError("voice.rewrite_model is required for automatic script shortening")
        if int(settings.get("audio_sample_rate",RATE))!=RATE:
            raise ValueError("Only 24000 Hz timeline audio is supported in Stage 4")

        doc,blocks=_read_source(context)
        ingest=context["previous"].get("ingest",{})
        duration=float(ingest.get("duration") or blocks[-1]["end"])
        if not math.isfinite(duration) or duration<=0 or duration+0.01<blocks[-1]["end"]:
            raise ValueError("Source video duration cannot be shorter than spoken idea timeline")
        if duration > 8*3600:
            raise ValueError("Source video exceeds Stage 4's 8-hour safeguard")
        fingerprint=_signature(doc,settings,duration)
        out=Path(context["folder"])/"voice"
        cache=out/".cache"/fingerprint[:24]
        cache.mkdir(parents=True,exist_ok=True)

        # Lazy API authentication: all existing cached audio can be reused offline.
        measures=[]
        generated=0
        reused=0
        normalized=[]
        final_blocks=[]
        revisions=0
        for block in blocks:
            start,end=float(block["start"]),float(block["end"])
            slot=end-start
            last_long_length=0.0
            final_len=0.0
            for revision_index in range(max_rewrites+1 if auto_shorten else 1):
                if revision_index == 0:
                    narration=block["narration"]
                    raw=cache/f"{block['id']:04d}_tts_raw.wav"
                else:
                    revision_file=cache/f"{block['id']:04d}_rewrite{revision_index}.json"
                    raw=cache/f"{block['id']:04d}_rewrite{revision_index}_raw.wav"
                    if revision_file.is_file():
                        narration=json.loads(revision_file.read_text(encoding="utf-8"))["narration"]
                    else:
                        proposal={**block,"narration":narration}
                        narration=self._revise(proposal,slot,last_long_length,rewrite_model)
                        _write_atomic(revision_file,json.dumps({
                            "narration":narration,"id":block["id"]},ensure_ascii=False)+"\n")
                    revisions+=1
                if not raw.is_file() or raw.stat().st_size<44:
                    tmp=raw.with_suffix(".part.wav")
                    try:
                        self._synthesize(narration,tmp,model,voice,instructions)
                        os.replace(tmp,raw)
                    finally:
                        tmp.unlink(missing_ok=True)
                    generated+=1
                else:
                    reused+=1
                orig=_wav_length(raw)
                if orig<.05:
                    raise ValueError(f"TTS produced near-empty audio for block {block['id']}")
                ratio=max(1.0,orig/slot*1.006)
                if ratio <= max_tempo+1e-6:
                    fitted=cache/f"{block['id']:04d}_revision{revision_index}_fitted.wav"
                    final_len=_normalize(raw,fitted,ratio)
                    break
                last_long_length=orig
                if revision_index >= max_rewrites or not auto_shorten:
                    raise ValueError(
                        f"Hindi voice block {block['id']} took {orig:.2f}s for a "
                        f"{slot:.2f}s slot and still needs {ratio:.3f}x tempo (> {max_tempo:.2f}). "
                        "Automated shortening was unavailable or exhausted. "
                        "Raw audio is cached for an improved script retry."
                    )
            final_blocks.append({**block,"narration":narration,
                                  "auto_revised":revision_index>0,
                                  "revision_count":revision_index})
            if final_len > slot+.05:
                raise ValueError(f"FFmpeg voice block {block['id']} still overruns its time slot")
            if final_len < .03:
                raise ValueError("TTS output after normalization is empty")
            # Mild container/encoder timing differences are safe; never extend into next idea.
            if final_len>slot:
                final_len=slot
            measure={
                "id":block["id"],"start":start,"end":end,"slot_seconds":round(slot,3),
                "raw_duration_s":round(orig,3),"fitted_duration_s":round(final_len,3),
                "tempo_factor":round(ratio,4),"audio_cached":raw.is_file(),
                "needs_human_voice_quality_review":True,
            }
            measures.append(measure)
            normalized.append(fitted)

        # Build the timeline exactly, with silence wherever the English speaker paused.
        total_frames=round(duration*RATE)
        if total_frames*2>MAX_AUDIO_BYTES:
            raise ValueError("Output exceeds the configured WAV memory guard")
        timeline=array("h",[0])*total_frames
        for item,path in zip(measures,normalized):
            sample_start=round(item["start"]*RATE)
            clip=_pcm_audio(path)
            allowed=max(0,round(item["slot_seconds"]*RATE))
            clip=clip[:allowed]
            if sample_start+len(clip)>total_frames:
                raise ValueError("TTS clip exceeds source video duration")
            timeline[sample_start:sample_start+len(clip)]=clip

        final_audio=out/"hindi_voice.wav"
        temp_audio=out/"hindi_voice.temporary.wav"
        _save_pcm(timeline,temp_audio)
        os.replace(temp_audio,final_audio)

        previous_json=context["previous"]["translate"].get("hindi_json")
        source_cues=(json.loads(Path(previous_json).read_text(encoding="utf-8")).get("segments",[])
                     if previous_json and Path(previous_json).is_file() else [])
        captions=_srt_from_audio(final_blocks,measures,source_cues)
        final_script_json=out/"hindi_voice_script_final.json"
        final_script_txt=out/"hindi_voice_script_final.txt"
        _write_atomic(final_script_json,json.dumps({
            "language":"hi","source_script_fingerprint":doc.get("fingerprint"),
            "blocks":final_blocks,"automatically_revised_blocks":sum(
                b["auto_revised"] for b in final_blocks),
        },ensure_ascii=False,indent=2)+"\n")
        _write_atomic(final_script_txt,"\n\n".join(b["narration"] for b in final_blocks)+"\n")
        estimate_srt=out/"hindi_tts_estimated.srt"
        estimate_json=out/"hindi_tts_estimated.json"
        report_file=out/"voice_report.json"
        save_srt(captions,estimate_srt)
        _write_atomic(estimate_json,json.dumps({
            "language":"hi","alignment":"estimated_inside_measured_block_not_word_aligned",
            "source_script_fingerprint":doc.get("fingerprint"),
            "segments":captions},ensure_ascii=False,indent=2)+"\n")
        report={
            "stage":"voice","status":"completed",
            "provider":"openai","model":model,"voice":voice,
            "sample_rate_hz":RATE,"channels":1,"sample_width_bytes":2,
            "total_duration_s":round(duration,3),
            "spoken_blocks":len(blocks),
            "api_requests_this_run":generated,
            "cached_blocks_this_run":reused,
            "maximum_tempo_used":max(x["tempo_factor"] for x in measures),
            "source_script_fingerprint":doc.get("fingerprint"),
            "fingerprint":fingerprint,
            "blocks":measures,
            "automatically_revised_ideas":sum(b["auto_revised"] for b in final_blocks),
            "revision_attempts":revisions,
            "auto_shorten_enabled":auto_shorten,
            "warnings":[
                "TTS voice quality and Indian Hindi accent have NOT been assessed by a human.",
                "TTS subtitles are approximate within each measured block; not word-aligned.",
                "Automatically shortened scripts preserve meaning by model instruction and basic validation only; semantic fidelity is not independently guaranteed.",
                "The output is an audio WAV only; video rendering and publishing are not included.",
                "Built-in OpenAI voices support Hindi text but are optimized for English.",
            ],
        }
        _write_atomic(report_file,json.dumps(report,ensure_ascii=False,indent=2)+"\n")
        return {
            "hindi_voice_wav":str(final_audio),
            "hindi_voice_script_final_json":str(final_script_json),
            "hindi_voice_script_final_txt":str(final_script_txt),
            "voice_report":str(report_file),
            "hindi_tts_estimated_srt":str(estimate_srt),
            "hindi_tts_estimated_json":str(estimate_json),
            "fingerprint":fingerprint,"blocks":len(blocks),
            "provider":"openai","api_requests":generated,"cached_blocks":reused,
        }
