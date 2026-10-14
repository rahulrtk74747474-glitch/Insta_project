"""Opt-in official Instagram/YouTube publication. No browser login or cookie scraping."""
from __future__ import annotations
import os
import time
from pathlib import Path
from urllib.parse import urlparse

import requests

GRAPH_VERSION = os.environ.get("META_GRAPH_VERSION", "v24.0")


def require_credentials():
    required=("META_IG_USER_ID","META_ACCESS_TOKEN","YOUTUBE_CLIENT_ID",
              "YOUTUBE_CLIENT_SECRET","YOUTUBE_REFRESH_TOKEN")
    missing=[name for name in required if not os.environ.get(name)]
    if missing:
        raise RuntimeError("Publishing disabled: missing secrets " + ", ".join(missing))


def check(response):
    response.raise_for_status()
    payload=response.json()
    if isinstance(payload,dict) and payload.get("error"):
        raise RuntimeError("Meta API error: "+str(payload["error"].get("message","unknown")))
    return payload


def instagram_reel(file,caption):
    """Upload a local MP4 through Instagram's official resumable Reels API."""
    file=Path(file)
    ig=os.environ["META_IG_USER_ID"]; token=os.environ["META_ACCESS_TOKEN"]
    root="https://graph.facebook.com/"+GRAPH_VERSION
    created=check(requests.post(
        f"{root}/{ig}/media",data={
            "media_type":"REELS","upload_type":"resumable",
            "caption":caption,"share_to_feed":"true","access_token":token
        },timeout=40))
    container=created["id"]
    upload_uri=created.get("uri",f"https://rupload.facebook.com/ig-api-upload/{container}")
    parsed=urlparse(upload_uri)
    if parsed.scheme!="https" or parsed.hostname!="rupload.facebook.com":
        raise RuntimeError("Unexpected Meta upload host")
    with file.open("rb") as src:
        check(requests.post(upload_uri,headers={
            "Authorization":"OAuth "+token,
            "offset":"0","file_size":str(file.stat().st_size),
            "Content-Type":"application/octet-stream"
        },data=src,timeout=300))
    for _ in range(40):
        state=check(requests.get(f"{root}/{container}",
                                 params={"fields":"status_code","access_token":token},
                                 timeout=30))
        if state.get("status_code")=="FINISHED":
            break
        if state.get("status_code") in ("ERROR","EXPIRED"):
            raise RuntimeError("Instagram processing failed: "+str(state))
        time.sleep(5)
    else:
        raise TimeoutError("Instagram reel did not finish processing")
    response=check(requests.post(f"{root}/{ig}/media_publish",
                   data={"creation_id":container,"access_token":token},timeout=60))
    media_id=response["id"]
    try:
        details=check(requests.get(f"{root}/{media_id}",
             params={"fields":"permalink","access_token":token},timeout=30))
        return {"id":media_id,"url":details.get("permalink","")}
    except requests.RequestException:
        return {"id":media_id,"url":""}


def youtube_short(file,title,description):
    """YouTube videos.insert with existing OAuth refresh token; visibility must be verified."""
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    credentials=Credentials(
        token=None,refresh_token=os.environ["YOUTUBE_REFRESH_TOKEN"],
        token_uri="https://oauth2.googleapis.com/token",
        client_id=os.environ["YOUTUBE_CLIENT_ID"],
        client_secret=os.environ["YOUTUBE_CLIENT_SECRET"],
        scopes=["https://www.googleapis.com/auth/youtube.upload"])
    credentials.refresh(Request())
    service=build("youtube","v3",credentials=credentials,cache_discovery=False)
    request=service.videos().insert(
        part="snippet,status",
        body={"snippet":{"title":title[:100],"description":description,
              "categoryId":"27","defaultLanguage":"hi"},
              "status":{"privacyStatus":os.getenv("YOUTUBE_PRIVACY","private"),
                        "selfDeclaredMadeForKids":False}},
        media_body=MediaFileUpload(str(file),mimetype="video/mp4",resumable=True))
    response=None
    while response is None:
        _, response=request.next_chunk()
    return {"id":response["id"],"url":"https://www.youtube.com/watch?v="+response["id"],
            "privacy":response.get("status",{}).get("privacyStatus","unknown")}
