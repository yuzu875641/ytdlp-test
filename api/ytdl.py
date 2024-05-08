from uuid import uuid4
from typing import Iterable

from flask import Flask, jsonify, request
from yt_dlp import YoutubeDL, DownloadError

PREFIX = "/api/ytdl"

users = {"admin": "password"}
login_users: dict[str, str] = {}
app = Flask(__name__)

ytdlopts = {
    "color": "no_color",
    "format": "bestaudio/93/best",
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
    return "Hello, World!"


@app.route(PREFIX + "/login", methods=["GET", "POST"])
def login():
    if not login_users:
        return "No users available", 401

    username = (
        request.args.get("username")
        if request.method == "GET"
        else request.form.get("username")
    )
    password = (
        request.args.get("password")
        if request.method == "GET"
        else request.form.get("password")
    )

    if username in users and users[username] == password:
        token = str(uuid4())
        login_users[token] = username
        return token

    return "", 401


def extract_info(
    extractor: YoutubeDL, url=None, video_id=None, process: bool | str | None = True
):
    if not url and not video_id:
        return jsonify({"error": "No url or video_id provided"}), 400

    process = str_to_bool(process)
    if video_id:
        url = f"https://www.youtube.com/watch?v={video_id}"

    try:
        info = extractor.extract_info(url, download=False, process=process)
    except DownloadError as e:
        return jsonify({"error": str(e)}), 400
    except Exception:
        return jsonify({"error": "Failed to download"}), 500

    if info is None:
        return jsonify({"error": "Failed to extract info"}), 500

    info["is_search"] = info.get("extractor", "").find("search") != -1
    return jsonify(info)


def require_argument(arguments: Iterable[str]):
    """Decorator that checks if the given argument name is present in the request JSON,
    and raises a 400 error if not.
    """

    def decorator(func):
        def wrapper(*args, **kwargs):
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


@app.post(PREFIX + "/query")
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


@app.post(PREFIX + "/get_stream")
@require_argument(["url"])
def get_stream(url: str):
    return extract_info(get_extractor(), url=url, process=True)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)
