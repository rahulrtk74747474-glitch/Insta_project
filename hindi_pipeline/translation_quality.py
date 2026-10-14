"""Deterministic Hindi translation timing/glossary validation for Stage 3.

Timing estimates are *not* synthesized speech durations. Stage 4 must validate TTS.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import unicodedata
from pathlib import Path

REVISION = "stage3.1"
DEVANAGARI = re.compile(r"[\u0904-\u0939\u0958-\u0961]")
NONSPACE = re.compile(r"\S")


def safe_single_line(value: str) -> str:
    value = re.sub(r"[\u0000-\u001f\u007f\u200b\u200c\u200d]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def check_english_segments(raw: dict) -> list[dict]:
    segments = raw.get("segments")
    if not isinstance(segments, list) or not segments:
        raise ValueError("English JSON must contain nonempty segments")
    result, last_end = [], 0.0
    seen = set()
    for cue in segments:
        idx = cue.get("id")
        if type(idx) is not int or idx < 1 or idx in seen:
            raise ValueError(f"Duplicate/invalid English segment ID: {idx!r}")
        seen.add(idx)
        start, end = float(cue["start"]), float(cue["end"])
        if not all(math.isfinite(x) for x in (start, end)) or start < 0 or end <= start:
            raise ValueError(f"Invalid English time interval at ID {idx}")
        if start < last_end - .004:
            raise ValueError(f"Overlapping English cues at ID {idx}")
        last_end = end
        text = safe_single_line(str(cue.get("text") or ""))
        if not text:
            raise ValueError(f"Empty English text at ID {idx}")
        result.append({"id": idx, "start": start, "end": end, "text": text})
    if [row["id"] for row in result] != sorted(seen):
        raise ValueError("English segment IDs must be sorted")
    return result


def glossary_matches(source: str, glossary: dict[str, str]) -> dict[str, str]:
    matches = {}
    for english, hindi in glossary.items():
        if not isinstance(english, str) or not isinstance(hindi, str) or not english.strip() or not hindi.strip():
            raise ValueError("Glossary must map nonempty terms to nonempty Hindi renderings")
        # Whole term with flexible internal whitespace, bounded by word boundaries.
        pattern = r"(?<!\w)" + r"\s+".join(re.escape(part) for part in english.strip().split()) + r"(?!\w)"
        if re.search(pattern, source, re.IGNORECASE):
            matches[english] = hindi
    return matches


def approximate_speech_seconds(text: str) -> float:
    """Heuristic only: Hindi script letters and word count approximate read-aloud length."""
    words = [w for w in safe_single_line(text).split() if w]
    hindi_units = sum(
        1 for ch in text if DEVANAGARI.fullmatch(ch)
    )
    # Matras do not add a syllable. Explicit virama joins conjunct consonants.
    joiners = text.count("\u094d")
    latin_units = sum(1 for ch in text if "a" <= ch.lower() <= "z")
    units = max(0, hindi_units - joiners) + .35 * latin_units
    return round(max(len(words) / 3.0, units / 7.4), 3)


def validate_hindi(english: list[dict], items: list[dict], glossary: dict,
                   speed_tolerance: float = 1.15) -> tuple[list[dict], dict]:
    expected = [row["id"] for row in english]
    if not isinstance(items, list) or len(items) != len(expected):
        raise ValueError("LLM returned the wrong number of subtitles")
    received = [item.get("id") for item in items]
    if received != expected:
        raise ValueError(f"LLM changed, duplicated or reordered subtitle IDs: {received}")
    output = []
    problems = []
    for en, item in zip(english, items):
        translated = safe_single_line(str(item.get("text", "")))
        idx = en["id"]
        length = en["end"] - en["start"]
        if not translated or not DEVANAGARI.search(translated):
            problems.append({"id": idx, "reason": "Missing Hindi Devanagari text"})
        required = glossary_matches(en["text"], glossary)
        missing = [target for target in required.values() if target.casefold() not in translated.casefold()]
        if missing:
            problems.append({"id": idx, "reason": "Glossary term missing", "expected_terms": missing})
        estimate = approximate_speech_seconds(translated)
        ratio = round(estimate / length, 3)
        if ratio > speed_tolerance:
            problems.append({"id": idx, "reason": "Estimated spoken Hindi exceeds slot",
                             "estimated_seconds": estimate, "available_seconds": round(length, 3)})
        output.append({
            "id": idx, "start": en["start"], "end": en["end"],
            "text": translated, "english": en["text"],
            "estimated_speech_seconds": estimate,
            "estimated_speed_ratio": ratio,
            "glossary_terms": required,
        })
    return output, {"problems": problems,
                    "estimated_over_limit": sum(p["reason"]=="Estimated spoken Hindi exceeds slot" for p in problems)}


def fingerprint(english_data: dict, model: str, glossary: dict, batch_size: int, tolerance: float) -> str:
    payload = {"revision": REVISION, "english": english_data.get("segments", []),
               "model": model, "glossary": glossary, "batch_size": batch_size,
               "speed_tolerance": tolerance}
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def translation_fingerprint(context: dict) -> str:
    settings = context["config"].get("translation", {})
    raw = json.loads(Path(context["previous"]["transcribe"]["english_json"]).read_text(encoding="utf-8"))
    return fingerprint(raw, settings.get("model", ""), settings.get("glossary", {}),
                       int(settings.get("batch_size", 8)), float(settings.get("speed_tolerance", 1.15)))
