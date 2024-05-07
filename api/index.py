from uuid import uuid4

from flask import Flask, jsonify, request
from yt_dlp import YoutubeDL, DownloadError

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
    "default_search": "ytsearch5",
    "source_address": "0.0.0.0",
}
ytdl = YoutubeDL(ytdlopts)


def str_to_bool(s: str | bool | None) -> bool:
    if s is None:
        return False

    if isinstance(s, bool):
        return s

    if s.lower() in ("yes", "true", "t", "y", "1"):
        return True

    return False


@app.route("/")
def index():
    return "Hello, World!"


@app.route("/api/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        username = request.args.get("username")
        password = request.args.get("password")
    else:
        username = request.form.get("username")
        password = request.form.get("password")

    if username in users and users[username] == password:
        token = uuid4().hex
        login_users[token] = username
        return token
    else:
        return "", 401


def check_token(func):
    def wrapper(*args, **kwargs):
        if not users:
            return func(*args, **kwargs)

        token = request.args.get("token")
        if not token:
            token = request.form.get("token")

        if token and login_users.get(token):
            return func(*args, **kwargs)
        else:
            return jsonify({"error": "Invalid token"}), 401

    wrapper.__name__ = func.__name__

    return wrapper


def extract_info(url=None, video_id=None, process: bool | str | None = True):
    process = str_to_bool(process)
    if video_id:
        url = f"https://www.youtube.com/watch?v={video_id}"

    try:
        info = ytdl.extract_info(url, download=False, process=process)
    except DownloadError as e:
        return jsonify({"error": str(e)}), 400
    except Exception:
        return jsonify({"error": "Failed to download"}), 500

    if info is None:
        return jsonify({"error": "Failed to extract info"}), 500

    return jsonify(info)


@app.route("/api/video/<string:video_id>")
@check_token
def ytdl_api(video_id: str):
    return extract_info(video_id=video_id, process=request.args.get("process"))


@app.route("/api/playlist/<string:playlist_id>")
@check_token
def ytdl_api_playlist(playlist_id: str):
    return extract_info(
        url=f"https://www.youtube.com/playlist?list={playlist_id}",
        process=request.args.get("process"),
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
