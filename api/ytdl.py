import json
import logging
import os
import time
import uuid
from io import StringIO
from pathlib import Path
from typing import Any, Iterable, MutableSet, cast

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
from upstash_redis import Redis
from upstash_redis.errors import UpstashError
from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError

# --- Constants ---
MAX_RESPONSE_SIZE = 1024 * 1024 * 4
RANGE_CHUNK_SIZE = 1024 * 1024 * 3
STREAM_CHUNK_SIZE = 512 * 1024
MAX_DOWNLOAD_FILESIZE = "200M"
API_PREFIX = "/api/ytdl"
RESPONSE_CACHE_TTL_SECONDS = 7200  # 2 hours for the full yt-dlp response
URL_CACHE_TTL_SECONDS = 1800  # 30 minutes for individual download URLs

# --- Initialization & Configuration ---
load_dotenv()
load_dotenv(find_dotenv(".env.local"))

app = Flask(
    __name__,
    template_folder=Path(__file__).parent.parent / "templates",
    static_folder=Path(__file__).parent.parent / "static",
)

formatter = logging.Formatter(
    "[%(asctime)s] [%(levelname)s] in %(module)s: %(message)s"
)
app.logger.handlers[0].setFormatter(formatter)
app.logger.setLevel(logging.INFO if not app.debug else logging.DEBUG)

app.config["KV_REST_API_URL"] = os.getenv("KV_REST_API_URL", "")
app.config["KV_REST_API_TOKEN"] = os.getenv("KV_REST_API_TOKEN", "")
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

# --- Redis & Cookie IO Setup ---
try:
    redis_client = Redis(
        url=app.config["KV_REST_API_URL"],
        token=app.config["KV_REST_API_TOKEN"],
        allow_telemetry=False,
    )
    redis_client.ping()
    app.logger.info("Successfully connected to Redis.")
except UpstashError as e:
    app.logger.critical(
        f"Could not connect to Redis: {e}. Caching and cookie persistence will be disabled."
    )
    redis_client = None


def debug_call_wrapper(func):
    def wrapper(*args, **kwargs):
        start_time = time.time()
        app.logger.info(f"Calling {func.__name__} with args: {args}, kwargs: {kwargs}")
        result = func(*args, **kwargs)
        elapsed = time.time() - start_time
        app.logger.info(
            f"{func.__name__} returned: {type(result)}, elapsed: {elapsed:.6f}s\nResult: {result}"
        )
        return result

    wrapper.__name__ = func.__name__
    return wrapper


class CookiesIOWrapper(StringIO):
    def __init__(self, redis_client: Redis | None, key: str = "ytdl_cookies"):
        self.redis_client = redis_client
        self.key = key
        initial_value = ""
        if self.redis_client:
            try:
                cookies_result = cast(str | None, self.redis_client.get(self.key))
                if cookies_result:
                    initial_value = cookies_result
                    app.logger.info("Successfully loaded cookies from Redis.")
            except UpstashError as e:
                app.logger.error(
                    f"Redis GET error: {e}. Proceeding without persistent cookies."
                )
        super().__init__(initial_value)

    def close(self):
        if self.redis_client:
            try:
                self.redis_client.set(self.key, self.getvalue())
                app.logger.info("Successfully saved cookies to Redis.")
            except UpstashError as e:
                app.logger.error(
                    f"Redis SET error: {e}. Cookies may not have been saved."
                )
        super().close()


cookies_io = CookiesIOWrapper(redis_client)
app.config["YTDL_OPTS"]["cookiefile"] = cookies_io


# --- Template Globals & Utils ---
@app.template_global("classlist")
class ClassList(MutableSet):
    def __init__(self, arg: str | Iterable | None = None, *args: str):
        classes: Iterable[str] = []
        if isinstance(arg, str):
            classes = arg.split()
        elif isinstance(arg, Iterable):
            classes = arg
        elif arg is not None:
            raise TypeError("expected a string or string iterable")
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
    if isinstance(value, bool):
        return value
    return str(value).lower() in ("yes", "true", "t", "y", "1")


def create_ytdl_extractor(
    provider: str = "youtube", search_amount: int = 5, extra_opts: dict | None = None
) -> YoutubeDL:
    base_opts = app.config["YTDL_OPTS"].copy()
    config = {**base_opts, **(extra_opts or {})}
    search_prefixes = {
        "soundcloud": f"scsearch{search_amount}",
        "ytmusic": "https://music.youtube.com/search?q=",
    }
    config["default_search"] = search_prefixes.get(provider, f"ytsearch{search_amount}")
    if provider == "ytmusic":
        config["playlist_items"] = f"1-{search_amount}"
    cookies_io.seek(0)
    return YoutubeDL(config)


def create_error_response(
    message: str, code: int = 500, exc: Exception | None = None
) -> tuple[Response, int]:
    if exc:
        app.logger.error(f"Exception caught: {message}", exc_info=exc)
    else:
        app.logger.warning(f"Returning error to client: {message} (Code: {code})")
    if "No such format" in message or "Unsupported URL" in message:
        code = 404
    elif "Missing argument" in message or "Invalid" in message:
        code = 400
    return jsonify({"success": False, "error": message}), code


# --- Request Hooks & Routes ---
@app.before_request
def log_request_info():
    app.logger.info(f"Request: {request.method} {request.path}")
    if request.is_json and request.method == "POST":
        app.logger.info(f"Request JSON payload: {request.get_json()}")


@app.route(API_PREFIX + "/")
@debug_call_wrapper
def index():
    return render_template("index.jinja2")


@app.route(API_PREFIX + "/check", methods=["POST"])
@debug_call_wrapper
def check():
    data = cast(dict | None, request.get_json(silent=True))
    if not data:
        return create_error_response("Invalid JSON payload.", 400)

    request_type = data.get("type", "video")
    has_ffmpeg = str_to_bool(data.get("has_ffmpeg", False))

    query = data.get("query")
    if not query:
        return create_error_response("Missing required argument: query", 400)

    cache_key = None
    if redis_client:
        try:
            cache_key = f"ytdl:cache:{query}:{request_type}:{has_ffmpeg}"
            cached_response = redis_client.get(cache_key)
            if cached_response and isinstance(cached_response, str):
                app.logger.info(f"Cache HIT for key: {cache_key}")
                return jsonify(json.loads(cached_response))
            app.logger.info(f"Cache MISS for key: {cache_key}")
        except UpstashError as e:
            app.logger.error(
                f"Redis cache check failed: {e}. Proceeding without cache."
            )

    try:
        format_selector = _build_check_format_string(
            req_type=request_type,
            has_ffmpeg=has_ffmpeg,
            custom_format=data.get("format", ""),
        )
    except ValueError as e:
        return create_error_response(str(e), 400, exc=e)

    extractor = create_ytdl_extractor(
        extra_opts={"noplaylist": True, "format": format_selector}
    )
    try:
        info = extractor.extract_info(query, download=False, process=True)
        if not info:
            return create_error_response(
                "yt-dlp failed to extract info (returned None).", 500
            )
    except DownloadError as e:
        return create_error_response(f"Extraction failed: {e}", 500, exc=e)

    ret_data = {
        "title": info.get("title", info.get("id", "")),
        "ext": info.get("ext", "bin"),
    }

    if str_to_bool(data.get("has_ffmpeg", False)) and "requested_formats" in info:
        ret_data["needFFmpeg"] = True
        req_formats = []
        for i in info.get("requested_formats", []):
            # For each stream, create a UID, cache the URL, and add the UID to the response.
            uid = uuid.uuid4().hex[:12]
            if redis_client:
                redis_client.set(f"ytdl:url:{uid}", i["url"], ex=URL_CACHE_TTL_SECONDS)

            req_formats.append(
                {
                    "id": uid,
                    "ext": i["ext"],
                    "formatId": i.get("format_id", "0"),
                    "fileSizeApprox": i.get("filesize_approx", 0),
                    "isPart": i.get("filesize_approx", 0) >= MAX_RESPONSE_SIZE,
                    "type": "audio" if i.get("audio_channels") else "video",
                }
            )
        ret_data["requestedFormats"] = req_formats
    else:
        url = info.get("url")
        if not url:
            return create_error_response(
                "No downloadable URL found for the selected format.", 404
            )
        # For single files, create a UID, cache the URL, and add the UID to the response.
        uid = uuid.uuid4().hex[:12]
        if redis_client:
            redis_client.set(f"ytdl:url:{uid}", url, ex=URL_CACHE_TTL_SECONDS)

        ret_data["id"] = uid
        if (filesize := info.get("filesize_approx", 0)) >= MAX_RESPONSE_SIZE:
            ret_data["isPart"] = True
            ret_data["fileSizeApprox"] = filesize

    if redis_client and cache_key:
        try:
            # Store the main response object (containing UIDs) with a 2-hour TTL.
            redis_client.set(
                cache_key, json.dumps(ret_data), ex=RESPONSE_CACHE_TTL_SECONDS
            )
            app.logger.info(f"Successfully cached response for key: {cache_key}")
        except UpstashError as e:
            app.logger.error(f"Redis cache set failed: {e}")

    return jsonify(ret_data)


@app.route(API_PREFIX + "/download")
@debug_call_wrapper
def download():
    uid = request.args.get("id")
    if not uid:
        return create_error_response("Missing required argument: id", 400)

    # The download URL is now retrieved from Redis using the UID.
    url = None
    if redis_client:
        try:
            url = redis_client.get(f"ytdl:url:{uid}")
        except UpstashError as e:
            return create_error_response("Failed to connect to cache.", 500, exc=e)

    if not url:
        return create_error_response(
            "Download link expired or invalid. Please try again.", 410
        )  # 410 Gone

    range_header = request.headers.get("Range")
    if range_header:
        app.logger.info(
            f"Handling range request for id '{uid}' with range: {range_header}"
        )
        return _range_download_handler(url, range_header)

    app.logger.info(f"Handling full file request for id '{uid}'")
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
                app.logger.info(f"Yielding chunk of size: {len(chunk)}")
                yield chunk

        return Response(
            stream_with_context(generate()),
            content_type=r.headers.get("Content-Type", "application/octet-stream"),
        )
    except requests.exceptions.RequestException as e:
        return create_error_response(f"Failed to download content: {e}", 502, exc=e)


# --- Helper Functions ---
def _build_check_format_string(
    req_type: str, has_ffmpeg: bool, custom_format: str
) -> str:
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


def _range_download_handler(url: str, range_header: str):
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
                app.logger.info(f"Yielding chunk of size: {len(chunk)}")
                yield chunk

        return Response(
            stream_with_context(generate()), headers=resp_headers, status=r.status_code
        )
    except requests.exceptions.RequestException as e:
        return create_error_response(
            f"Failed to download content range: {e}", 502, exc=e
        )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)
