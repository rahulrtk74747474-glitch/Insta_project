"""Deterministic caption segmentation that preserves every Whisper word and its timings.

This module does not rewrite transcript content. Durations are for on-screen captions;
original word boundaries remain recorded for translation and future audio alignment.
"""
from __future__ import annotations
import json
import math
import re
from pathlib import Path

END = re.compile(r'[.!?。！？]+["\'”’)]*$')
CLAUSE = re.compile(r"[,;:—]$")


def normalized_words(payload):
    words = []
    for segment in payload["segments"]:
        for item in segment.get("words", []):
            token = str(item.get("word", "")).strip()
            if not token:
                continue
            start, end = float(item["start"]), float(item["end"])
            if not (math.isfinite(start) and math.isfinite(end) and start >= 0 and end >= 0):
                continue
            words.append({
                "word": token, "start": start, "end": end,
                "probability": item.get("probability"),
                "timing_estimated": bool(item.get("timing_estimated", False) or end <= start),
            })
    words.sort(key=lambda word: (word["start"], word["end"]))
    repaired = 0
    for i, word in enumerate(words):
        if word["end"] <= word["start"]:
            next_start = words[i+1]["start"] if i+1 < len(words) else word["start"] + 0.08
            # A tiny interval is an *estimate*, never a measured Whisper time.
            word["end"] = round(min(word["start"] + 0.08,
                                    max(word["start"] + 0.01, next_start)), 3)
            word["timing_estimated"] = True
            repaired += 1
    return words, repaired


def phrase(words):
    result = " ".join(item["word"].strip() for item in words)
    result = re.sub(r"\s+([,.:;!?।॥])", r"\1", result)
    return re.sub(r'\s+(["”’])', r"\1", result).strip()


def split_lines(text, width=42):
    if len(text) <= width:
        return [text]
    tokens = text.split()
    options = []
    for index in range(1, len(tokens)):
        first, second = " ".join(tokens[:index]), " ".join(tokens[index:])
        if len(first) <= width and len(second) <= width:
            penalty = abs(len(first)-len(second)) * .09
            if first.endswith((",", ":", ";", "—")):
                penalty -= 1.7
            options.append((penalty, first, second))
    if options:
        _, first, second = min(options)
        return [first, second]
    spaces = [m.start() for m in re.finditer(" ", text)]
    if not spaces:
        return [text]
    position = min(spaces, key=lambda idx: abs(idx - len(text)/2))
    return [text[:position], text[position+1:]]


def cue_cost(words, first, last):
    chunk = words[first:last]
    text = phrase(chunk)
    duration = max(.16, chunk[-1]["end"] - chunk[0]["start"])
    gap_after = words[last]["start"]-chunk[-1]["end"] if last < len(words) else 1.5
    if duration > 6.4 or len(text) > 82 or len(chunk) > 23:
        return math.inf
    score = 5.5
    score += max(0, 1.30-duration)**2*11
    score += max(0, duration-4.3)**2*3
    score += max(0, len(text)-74)**2*.045
    score += max(0, len(text)/duration-17.5)**2*.35
    score += abs(len(text)-54)*.025
    score += 4.0 if len(chunk) <= 2 else 0
    max_internal_gap = max((words[i+1]["start"]-words[i]["end"]
                            for i in range(first,last-1)), default=0)
    score += max(0, max_internal_gap-.36)*9
    if END.search(chunk[-1]["word"]):
        score -= 3.5
    elif CLAUSE.search(chunk[-1]["word"]):
        score -= 1.2
    if gap_after > .18:
        score -= min(3, (gap_after-.18)*5)
    if last == len(words):
        score -= 2
    return score


def optimize(payload, media_duration=None):
    words, repairs = normalized_words(payload)
    if not words:
        raise ValueError("No usable word timestamps")
    total = len(words)
    best = [math.inf]*(total+1)
    nxt = [None]*(total+1)
    best[total] = 0
    for i in range(total-1,-1,-1):
        for j in range(i+1,min(total,i+23)+1):
            if j>i+1 and words[j-1]["start"]-words[j-2]["end"]>1.10:
                break
            cost = cue_cost(words,i,j)
            if math.isfinite(cost) and cost+best[j]<best[i]:
                best[i],nxt[i] = cost+best[j],j
        if nxt[i] is None:
            raise ValueError(f"Unable to group recognized words at index {i}")
    chunks = []
    cursor = 0
    while cursor < total:
        dest = nxt[cursor]
        chunks.append(words[cursor:dest])
        cursor = dest
    cues = []
    for i, chunk in enumerate(chunks):
        onset,offset = chunk[0]["start"],chunk[-1]["end"]
        previous_end = chunks[i-1][-1]["end"] if i else 0
        next_start = chunks[i+1][0]["start"] if i+1<len(chunks) else (
            media_duration if media_duration is not None else offset+.25)
        start = max(0, onset-.15, previous_end+.01)
        end = min(next_start-.025,offset+.28,
                  media_duration if media_duration is not None else offset+.28)
        if end <= start:
            start = max(0,onset-.02)
            end = max(start+.02,offset)
        content = phrase(chunk)
        cues.append({
            "id":i+1,"start":round(start,3),"end":round(end,3),
            "text":content,"display_lines":split_lines(content),
            "words":chunk,"original_start":onset,"original_end":offset
        })
    for i in range(1,len(cues)):
        if cues[i]["start"]<cues[i-1]["end"]:
            cues[i-1]["end"] = max(cues[i-1]["start"]+.01,
                                   round(cues[i]["start"]-.01,3))
    return cues,{"input_words":total,"timing_repairs":repairs,"output_cues":len(cues)}


def timestamp(seconds):
    milliseconds = max(0,round(seconds*1000))
    hh,rest=divmod(milliseconds,3600000)
    mm,rest=divmod(rest,60000)
    ss,ms=divmod(rest,1000)
    return f"{hh:02}:{mm:02}:{ss:02},{ms:03}"


def save_srt(cues, destination):
    body="\n\n".join(
        f"{i}\n{timestamp(cue['start'])} --> {timestamp(cue['end'])}\n"
        + "\n".join(cue["display_lines"])
        for i,cue in enumerate(cues,1))
    Path(destination).write_text(body+"\n",encoding="utf-8")


def metrics(cues):
    if not cues:
        return {}
    lengths=[cue["end"]-cue["start"] for cue in cues]
    speeds=[len(cue["text"])/max(.01,d) for cue,d in zip(cues,lengths)]
    return {
        "cues":len(cues),
        "words":sum(len(cue.get("words",[])) for cue in cues),
        "shorter_than_0_8s":sum(d<.8 for d in lengths),
        "cps_over_18":sum(s>18 for s in speeds),
        "cps_over_22":sum(s>22 for s in speeds),
        "mean_characters_per_second":round(sum(speeds)/len(speeds),2),
        "two_line_cues":sum(len(cue.get("display_lines",[]))==2 for cue in cues),
        "overlapping_cues":sum(cues[i]["start"]<cues[i-1]["end"]
                                for i in range(1,len(cues))),
        "start_s":cues[0]["start"],"end_s":cues[-1]["end"],
        "max_line_chars":max(len(line) for cue in cues
                              for line in cue.get("display_lines",[cue["text"]])),
        "total_chars":sum(len(cue["text"]) for cue in cues)
    }
