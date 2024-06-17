import os
from typing import Iterable
from base64 import b64decode, b64encode

from flask import (
    Flask,
    Response,
    jsonify,
    request,
    render_template,
    stream_with_context,
)
import requests
from yt_dlp import YoutubeDL, DownloadError


BASEDIR = os.path.dirname(os.path.abspath(__file__))
PREFIX = "/api/ytdl"

app = Flask(
    __name__,
    template_folder=os.path.join(BASEDIR, *[os.path.pardir, "templates"]),
    static_folder=os.path.join(BASEDIR, *[os.path.pardir, "static"]),
)
ytdlopts = {
    "color": "no_color",
    "outtmpl": r"downloads/%(extractor)s-%(id)s-%(title)s.%(ext)s",
    "restrictfilenames": True,
    "nocheckcertificate": True,
    "ignoreerrors": False,
    "logtostderr": False,
    "quiet": True,
    "extract_flat": "in_playlist",
    "no_warnings": True,
    "source_address": "0.0.0.0",
}


def get_extractor(
    config: dict | None = None, provider: str = "youtube", search_amount: int = 5
) -> YoutubeDL:
    if config is None:
        config = ytdlopts
    else:
        config = {**ytdlopts, **config}

    match provider:
        case "soundcloud":
            config["default_search"] = f"scsearch{search_amount}"
        case "ytmusic":
            config.update(
                {
                    "default_search": "https://music.youtube.com/search?q=",
                    "playlist_items": f"1-{search_amount}",
                }
            )
        case _:
            config["default_search"] = f"ytsearch{search_amount}"

    return YoutubeDL(config)


def str_to_bool(value: str | bool | None) -> bool:
    if value is None:
        return False

    if isinstance(value, bool):
        return value

    return value.lower() in ("yes", "true", "t", "y", "1")


@app.route(PREFIX)
def index():
    return render_template("index.html")


# @app.route(PREFIX + "/login", methods=["GET", "POST"])
# def login():
#     if not login_users:
#         return "No users available", 401

#     username = (
#         request.args.get("username")
#         if request.method == "GET"
#         else request.form.get("username")
#     )
#     password = (
#         request.args.get("password")
#         if request.method == "GET"
#         else request.form.get("password")
#     )

#     if username in users and users[username] == password:
#         token = str(uuid4())
#         login_users[token] = username
#         return token

#     return "", 401


def encode(str: str) -> str:
    return b64encode(str.encode("utf-8")).decode("utf-8")


def decode(str: str) -> str:
    return b64decode(str.encode("utf-8")).decode("utf-8")


def extract_info(
    extractor: YoutubeDL,
    url: str | None = None,
    video_id: str | None = None,
    process: bool | str | None = True,
    return_dict: bool = False,
):
    """Extracts video information from url or video_id using the provided extractor.

    Args:
        extractor: YoutubeDL instance used to extract the info.
        url: The url of the video.
        video_id: The video id.
        process: Whether to process the video info.
        return_dict: Whether to return the info as a dictionary.

    Returns:
        The video information as a dictionary or a Response object with an error message.
    """

    process = str_to_bool(process)

    if not url and not video_id:
        return error_response("No url or video_id provided")

    if video_id:
        url = f"https://www.youtube.com/watch?v={video_id}"

    try:
        info = extractor.extract_info(url, download=False, process=process)
    except (DownloadError, Exception) as e:
        return error_response(str(e))

    if info is None:
        return error_response("Failed to extract info")

    info["is_search"] = "search" in info.get("extractor", "")

    return info if return_dict else jsonify(info)


def error_response(message: str):
    """Creates a Response object with an error message."""
    return jsonify({"error": message}), 400 if "No" in message else 500


def require_argument(arguments: Iterable[str]):
    """Decorator that checks if the given argument name is present in the request JSON,
    and raises a 400 error if not.
    """

    def decorator(func):
        def wrapper(*args, **kwargs):
            if request.method == "GET":
                json_data = request.args
            else:
                json_data = request.get_json(force=True, silent=True, cache=True)
                if not json_data:
                    return "Malformed JSON", 400

            for argument in arguments:
                if argument not in json_data:
                    return "Missing argument", 400
                kwargs[argument] = json_data[argument]

            return func(*args, **kwargs)

        wrapper.__name__ = func.__name__
        return wrapper

    return decorator


def check_arguments(arguments: Iterable[str]):
    def decorator(func):
        def wrapper(*args, **kwargs):
            if request.method == "GET":
                json_data = request.args
            else:
                json_data = request.get_json(force=True, silent=True, cache=True)
                if not json_data:
                    return "Malformed JSON", 400

            for argument in arguments:
                if argument not in json_data:
                    continue

                kwargs[argument] = json_data[argument]
            return func(*args, **kwargs)

        wrapper.__name__ = func.__name__
        return wrapper

    return decorator


@app.post(PREFIX + "/search")
@require_argument(["query"])
@check_arguments(["process", "provider", "search_amount"])
def search(
    query: str, process: bool = True, provider: str = "youtube", search_amount: int = 5
):
    return extract_info(
        get_extractor(provider=provider, search_amount=search_amount),
        url=query,
        process=process,
    )


@app.post(PREFIX + "/extract")
@require_argument(["url"])
def extract(url: str):
    return extract_info(get_extractor(), url=url)


@app.post(PREFIX + "/check")
@require_argument(["query"])
@check_arguments(["type"])
def check(query: str, type: str = "video"):
    info: dict = extract_info(
        get_extractor(
            config={
                "noplaylist": True,
                "format": "bestaudio[ext=m4a]/bestaudio[ext=webm]/bestaudio/best"
                if type == "audio"
                else "best[protocol^=http][protocol!*=dash]/best",
            }
        ),
        url=query,
        return_dict=True,
    )  # type: ignore

    if not isinstance(info, dict):
        return info

    url = info.get("url")
    if not url:
        return jsonify({"error": "No url found"}), 404

    chunk_size = 10 * 1024
    if info["downloader_options"].get("http_chunk_size"):
        chunk_size = int(info["downloader_options"]["http_chunk_size"]) // 5

    return jsonify(
        {
            "video_id": encode(url),
            "title": info.get("title", info.get("id", "")),
            "ext": info.get("ext", "bin"),
            "chunk_size": chunk_size,
        }
    )


@app.get(PREFIX + "/download")
@require_argument(["video_id"])
@check_arguments(["chunk_size"])
def download(video_id: str, chunk_size: int = 10 * 1024):
    url = decode(video_id)
    r = requests.get(url, headers={"Range": "bytes=0-"}, stream=True)
    if not r.ok:
        return jsonify({"error": "Download failed"}), r.status_code

    def wrapper():
        for chunk in r.iter_content(chunk_size=int(chunk_size)):
            print(len(chunk))
            yield chunk

    return Response(
        stream_with_context(wrapper()),
        content_type=r.headers.get("Content-Type", "application/octet-stream"),
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
