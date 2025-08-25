import os
from base64 import urlsafe_b64decode, urlsafe_b64encode
from io import StringIO
from pathlib import Path
from typing import Any, Iterable, MutableSet, cast

import redis
import redis.exceptions
import requests
from dotenv import find_dotenv, load_dotenv
from flask import (
    Flask,
    Response,
    jsonify,
    render_template,
    request,
    stream_with_context,
)
from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError

MAX_RESPONSE_SIZE = 1024 * 1024 * 4  # 4 MB - Vercel's response size limit
RANGE_CHUNK_SIZE = 1024 * 1024 * 3  # 3 MB - Size of chunks for partial downloads
STREAM_CHUNK_SIZE = 512 * 1024  # 512 KB - Chunk size for streaming responses
MAX_DOWNLOAD_FILESIZE = "200M"  # Max filesize yt-dlp will consider for extraction
API_PREFIX = "/api/ytdl"

load_dotenv()
load_dotenv(find_dotenv(".env.local"))

app = Flask(
    __name__,
    template_folder=Path(__file__).parent.parent / "templates",
    static_folder=Path(__file__).parent.parent / "static",
)

app.config["REDIS_URL"] = os.getenv("REDIS_URL", "redis://localhost:6379")
app.config["YTDL_OPTS"] = {
    "color": "no_color",
    "outtmpl": r"downloads/%(extractor)s-%(id)s-%(title)s.%(ext)s",
    "restrictfilenames": True,
    "nocheckcertificate": True,
    "ignoreerrors": False,
    "logtostderr": False,
    "quiet": True,
    "noplaylist": True,
    "no_warnings": True,
    "source_address": "0.0.0.0",
    "extractor_args": {
        "youtubepot-bgutilhttp": {
            "base_url": "https://bgutil-ytdlp-pot-vercal.vercel.app"
        }
    },
}


class CookiesIOWrapper(StringIO):
    """
    A file-like object that proxies yt-dlp's cookie operations to Redis.
    This allows for persistent cookies across serverless function invocations.
    """

    def __init__(self, redis_client: redis.Redis | None, key: str = "ytdl_cookies"):
        self.redis_client = redis_client
        self.key = key
        initial_value = ""
        if self.redis_client:
            try:
                cookies_result = cast(bytes | None, self.redis_client.get(self.key))
                if cookies_result:
                    initial_value = cookies_result.decode("utf-8")
            except redis.exceptions.RedisError as e:
                app.logger.error(
                    f"Redis GET error: {e}. Proceeding without persistent cookies."
                )
        super().__init__(initial_value)

    def close(self):
        """Saves the final cookie jar back to Redis upon closing."""
        if self.redis_client:
            try:
                self.redis_client.set(self.key, self.getvalue())
            except redis.exceptions.RedisError as e:
                app.logger.error(
                    f"Redis SET error: {e}. Cookies may not have been saved."
                )
        super().close()


try:
    redis_client = redis.Redis.from_url(
        app.config["REDIS_URL"], socket_connect_timeout=2
    )
    redis_client.ping()
    app.logger.info("Successfully connected to Redis.")
except redis.exceptions.ConnectionError as e:
    app.logger.critical(
        f"Could not connect to Redis: {e}. Cookie persistence will be disabled."
    )
    redis_client = None

cookies_io = CookiesIOWrapper(redis_client)
app.config["YTDL_OPTS"]["cookiefile"] = cookies_io


@app.template_global("classlist")
class ClassList(MutableSet):
    """Data structure for holding, and ultimately returning as a single string,
    a set of identifiers that should be managed like CSS classes.
    """

    def __init__(self, arg: str | Iterable | None = None, *args: str):
        classes: Iterable[str] = []
        if isinstance(arg, str):
            classes = arg.split()
        elif isinstance(arg, Iterable):
            classes = arg
        elif arg is not None:
            raise TypeError("expected a string or string iterable, got %r" % type(arg))

        self.classes = set(filter(None, classes))
        if args:
            self.classes.update(args)

    def __contains__(self, class_):
        return class_ in self.classes

    def __iter__(self):
        return iter(self.classes)

    def __len__(self):
        return len(self.classes)

    def add(self, *classes):  # type: ignore
        for class_ in classes:
            self.classes.add(class_)
        return ""

    def discard(self, *classes):  # type: ignore
        for class_ in classes:
            self.classes.discard(class_)
        return ""

    def __str__(self):
        return " ".join(sorted(self.classes))

    def __html__(self):
        return 'class="%s"' % self if self else ""


def str_to_bool(value: Any) -> bool:
    """Converts a variety of string-like values to a boolean."""
    if isinstance(value, bool):
        return value
    return str(value).lower() in ("yes", "true", "t", "y", "1")


def create_ytdl_extractor(
    provider: str = "youtube", search_amount: int = 5, extra_opts: dict | None = None
) -> YoutubeDL:
    """Factory function to create a configured YoutubeDL instance."""
    base_opts = app.config["YTDL_OPTS"].copy()
    config = {**base_opts, **(extra_opts or {})}

    search_prefixes = {
        "soundcloud": f"scsearch{search_amount}",
        "ytmusic": "https://music.youtube.com/search?q=",
    }
    config["default_search"] = search_prefixes.get(provider, f"ytsearch{search_amount}")

    if provider == "ytmusic":
        config["playlist_items"] = f"1-{search_amount}"

    cookies_io.seek(0)  # reset on each use
    return YoutubeDL(config)


def create_error_response(message: str, code: int = 500) -> tuple[Response, int]:
    """Creates a standardized JSON error response."""
    if "No such format" in message or "Unsupported URL" in message:
        code = 404
    elif "Missing argument" in message or "Invalid" in message:
        code = 400

    return jsonify({"success": False, "error": message}), code


@app.route(API_PREFIX + "/")
def index():
    return render_template("index.html")


@app.route(API_PREFIX + "/search", methods=["POST"])
def search():
    data = request.get_json(silent=True)
    if not data:
        return create_error_response("Invalid JSON payload.", 400)

    query = data.get("query")
    if not query:
        return create_error_response("Missing required argument: query", 400)

    extractor = create_ytdl_extractor(
        provider=data.get("provider", "youtube"),
        search_amount=int(data.get("search_amount", 5)),
    )

    try:
        info = extractor.extract_info(
            query, download=False, process=str_to_bool(data.get("process", True))
        )
        if not info:
            return create_error_response("Failed to extract info.", 500)

        info["is_search"] = "search" in info.get("extractor", "")
        info["success"] = True
        return jsonify(info)
    except DownloadError as e:
        app.logger.error(f"DownloadError during search for '{query}': {e}")
        return create_error_response(f"Extraction failed: {e}", 500)


def _build_check_format_string(
    req_type: str, has_ffmpeg: bool, custom_format: str
) -> str:
    """Helper to build the complex format selection string for yt-dlp."""
    if req_type == "video":
        if has_ffmpeg:
            format_str = f"{custom_format}/bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=1080][ext=mp4]/b"
        else:
            format_str = (
                f"{custom_format}/best*[vcodec!=none][acodec!=none][height<=1080]"
            )
    elif req_type == "audio":
        format_str = f"{custom_format}/bestaudio[ext=mp3]/bestaudio[ext=m4a]/bestaudio[ext=webm]/bestaudio"
    else:
        raise ValueError("Invalid type specified for format string.")

    format_str = format_str.lstrip("/")
    return f"({format_str}/best)[protocol^=http][protocol!*=dash][filesize<={MAX_DOWNLOAD_FILESIZE}]"


@app.route(API_PREFIX + "/check", methods=["POST"])
def check():
    data = request.get_json(silent=True)
    if not data:
        return create_error_response("Invalid JSON payload.", 400)

    query = data.get("query")
    if not query:
        return create_error_response("Missing required argument: query", 400)

    try:
        format_selector = _build_check_format_string(
            req_type=data.get("type", "video"),
            has_ffmpeg=str_to_bool(data.get("has_ffmpeg", False)),
            custom_format=data.get("format", ""),
        )
    except ValueError as e:
        return create_error_response(str(e), 400)

    extractor = create_ytdl_extractor(
        extra_opts={"noplaylist": True, "format": format_selector}
    )

    try:
        info = extractor.extract_info(query, download=False, process=True)
        if not info:
            return create_error_response("Failed to extract info.", 500)
    except DownloadError as e:
        app.logger.error(f"DownloadError during check for '{query}': {e}")
        return create_error_response(f"Extraction failed: {e}", 500)

    ret_data = {
        "title": info.get("title", info.get("id", "")),
        "ext": info.get("ext", "bin"),
    }

    if str_to_bool(data.get("has_ffmpeg", False)) and "requested_formats" in info:
        ret_data["needFFmpeg"] = True
        ret_data["requestedFormats"] = [
            {
                "videoId": urlsafe_b64encode(i["url"].encode()).decode(),
                "ext": i["ext"],
                "formatId": i.get("format_id", "0"),
                "fileSizeApprox": i.get("filesize_approx", 0),
                "isPart": i.get("filesize_approx", 0) >= MAX_RESPONSE_SIZE,
                "type": "audio" if i.get("audio_channels") else "video",
            }
            for i in info.get("requested_formats", [])
        ]
        return jsonify(ret_data)

    url = info.get("url")
    if not url:
        return create_error_response(
            "No downloadable URL found for the selected format.", 404
        )

    ret_data["videoId"] = urlsafe_b64encode(url.encode()).decode()
    if (filesize := info.get("filesize_approx", 0)) >= MAX_RESPONSE_SIZE:
        ret_data["isPart"] = True
        ret_data["fileSizeApprox"] = filesize

    return jsonify(ret_data)


def _range_download_handler(url: str, range_header: str):
    """Internal handler for streaming a specific byte range of a file."""
    try:
        start_byte_str = range_header.split("=")[-1].split("-")[0]
        start_byte = int(start_byte_str) if start_byte_str.isdigit() else 0
    except (IndexError, ValueError):
        start_byte = 0

    headers = {"Range": f"bytes={start_byte}-{start_byte + RANGE_CHUNK_SIZE}"}

    try:
        r = requests.get(url, headers=headers, stream=True, timeout=10)
        r.raise_for_status()

        resp_headers = {
            "Content-Type": r.headers.get("Content-Type", "application/octet-stream"),
            "Content-Length": r.headers.get("Content-Length", "0"),
            "Accept-Ranges": "bytes",
        }
        if "Content-Range" in r.headers:
            resp_headers["Content-Range"] = r.headers["Content-Range"]

        def generate():
            for chunk in r.iter_content(chunk_size=STREAM_CHUNK_SIZE):
                yield chunk

        return Response(
            stream_with_context(generate()), headers=resp_headers, status=r.status_code
        )

    except requests.exceptions.RequestException as e:
        app.logger.error(f"RequestException during range download: {e}")
        return create_error_response(f"Failed to download content range: {e}", 502)


@app.route(API_PREFIX + "/download")
def download():
    video_id = request.args.get("video_id")
    if not video_id:
        return create_error_response("Missing required argument: video_id", 400)
    try:
        url = urlsafe_b64decode(video_id.encode()).decode()
    except (ValueError, TypeError):
        return create_error_response("Invalid video_id.", 400)

    range_header = request.headers.get("Range")
    if range_header:
        return _range_download_handler(url, range_header)

    try:
        r = requests.get(url, stream=True, timeout=10)
        r.raise_for_status()

        content_length = int(r.headers.get("Content-Length", 0))
        if content_length >= MAX_RESPONSE_SIZE:
            return create_error_response(
                "File is too large for direct download. Client must use Range requests.",
                400,
            )

        def generate():
            for chunk in r.iter_content(chunk_size=STREAM_CHUNK_SIZE):
                yield chunk

        return Response(
            stream_with_context(generate()),
            content_type=r.headers.get("Content-Type", "application/octet-stream"),
        )
    except requests.exceptions.RequestException as e:
        app.logger.error(f"RequestException during full download: {e}")
        return create_error_response(f"Failed to download content: {e}", 502)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)
