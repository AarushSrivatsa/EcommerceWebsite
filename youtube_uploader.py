#!/usr/bin/env python3
"""Upload a local video to YouTube with metadata entered interactively."""

from __future__ import annotations

import mimetypes
import random
import sys
import time
from pathlib import Path

import httplib2
from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

BASE_DIR = Path(__file__).resolve().parent
CLIENT_SECRETS_FILE = BASE_DIR / "client_secret.json"
TOKEN_FILE = BASE_DIR / "token.json"
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
CHUNK_SIZE = 8 * 1024 * 1024  # 8 MiB; resumable upload
MAX_RETRIES = 5


def get_youtube_service():
    if not CLIENT_SECRETS_FILE.is_file():
        print(f"\nMissing OAuth credentials: {CLIENT_SECRETS_FILE}")
        print("Download your OAuth Desktop-app JSON from Google Cloud Console, "
              "put it beside this script, and name it client_secret.json.")
        sys.exit(1)

    credentials = None
    if TOKEN_FILE.is_file():
        try:
            credentials = Credentials.from_authorized_user_file(
                str(TOKEN_FILE), SCOPES
            )
        except (ValueError, OSError):
            credentials = None

    if credentials and not credentials.valid:
        if credentials.expired and credentials.refresh_token:
            try:
                credentials.refresh(Request())
            except RefreshError:
                credentials = None
        else:
            credentials = None

    if not credentials or not credentials.valid:
        flow = InstalledAppFlow.from_client_secrets_file(
            str(CLIENT_SECRETS_FILE), SCOPES
        )
        credentials = flow.run_local_server(port=0)

    TOKEN_FILE.write_text(credentials.to_json(), encoding="utf-8")
    try:
        TOKEN_FILE.chmod(0o600)
    except OSError:
        pass

    return build("youtube", "v3", credentials=credentials)


def ask_multiline_description() -> str:
    print("\nDescription (paste/type multiple lines; enter END on its own line when done):")
    lines: list[str] = []
    while True:
        try:
            line = input()
        except EOFError:
            break
        if line.strip() == "END":
            break
        lines.append(line)
    return "\n".join(lines).strip()


def prompt_metadata():
    while True:
        raw_path = input("Video file path: ").strip().strip("\"'")
        video_path = Path(raw_path).expanduser().resolve()
        if video_path.is_file():
            break
        print(f"File not found: {video_path}\nTry again.\n")

    title = input("Title (max 100 characters): ").strip()
    if not title:
        print("Title cannot be empty.")
        sys.exit(1)
    if len(title) > 100:
        print(f"Title is {len(title)} characters; YouTube titles can be at most 100.")
        sys.exit(1)

    description = ask_multiline_description()
    if len(description) > 5000:
        print(f"Description is {len(description)} characters; shorten it to 5000 or fewer.")
        sys.exit(1)

    raw_tags = input("Tags, separated by commas (optional): ").strip()
    tags = [tag.strip() for tag in raw_tags.split(",") if tag.strip()]

    category_id = input("Category ID [22 = People & Blogs]: ").strip() or "22"
    privacy = input("Visibility: private / unlisted / public [private]: ").strip().lower() or "private"
    if privacy not in {"private", "unlisted", "public"}:
        print("Visibility must be private, unlisted, or public.")
        sys.exit(1)

    return video_path, title, description, tags, category_id, privacy


def upload_video(youtube, video_path, title, description, tags, category_id, privacy):
    mime_type = mimetypes.guess_type(str(video_path))[0] or "application/octet-stream"
    if not (mime_type.startswith("video/") or mime_type == "application/octet-stream"):
        print(f"Warning: detected MIME type {mime_type!r}; YouTube may reject this file.")

    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags,
            "categoryId": category_id,
        },
        "status": {"privacyStatus": privacy},
    }
    media = MediaFileUpload(
        str(video_path), mimetype=mime_type, chunksize=CHUNK_SIZE, resumable=True
    )
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

    response = None
    retries = 0
    while response is None:
        try:
            status, response = request.next_chunk()
            if status:
                print(f"Upload progress: {int(status.progress() * 100)}%")
        except HttpError as exc:
            if exc.resp.status in {500, 502, 503, 504} and retries < MAX_RETRIES:
                delay = min(2 ** retries, 32) + random.random()
                print(f"Temporary YouTube API error ({exc.resp.status}); retrying in {delay:.1f}s...")
                time.sleep(delay)
                retries += 1
                continue
            raise
        except (OSError, httplib2.HttpLib2Error) as exc:
            if retries >= MAX_RETRIES:
                raise
            delay = min(2 ** retries, 32) + random.random()
            print(f"Temporary connection error ({exc}); retrying in {delay:.1f}s...")
            time.sleep(delay)
            retries += 1

    video_id = response.get("id")
    if not video_id:
        raise RuntimeError(f"Upload response did not contain a video ID: {response}")
    return f"https://www.youtube.com/watch?v={video_id}"


def main():
    print("=== Local YouTube Uploader ===")
    video_path, title, description, tags, category_id, privacy = prompt_metadata()

    print("\n--- Upload preview ---")
    print(f"File:        {video_path}")
    print(f"Title:       {title}")
    print(f"Description: {description[:250]}{'...' if len(description) > 250 else ''}")
    print(f"Tags:        {', '.join(tags) if tags else '(none)'}")
    print(f"Category ID: {category_id}")
    print(f"Visibility:  {privacy}")
    confirmation = input("\nType UPLOAD to start: ").strip()
    if confirmation != "UPLOAD":
        print("Cancelled; nothing was uploaded.")
        return

    try:
        youtube = get_youtube_service()
        print("\nUploading. Keep this terminal open until it finishes...")
        url = upload_video(
            youtube, video_path, title, description, tags, category_id, privacy
        )
        print(f"\nUpload request completed: {url}")
        print("YouTube may still need time to process the video before playback is available.")
    except HttpError as exc:
        print(f"\nYouTube API error ({exc.resp.status}): {exc.content.decode('utf-8', errors='replace')}")
        print("Check the Google Cloud API setup, OAuth permissions, quota, and file format.")
        sys.exit(1)
    except Exception as exc:
        print(f"\nUpload failed: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
