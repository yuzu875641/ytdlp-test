from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from random import randint
from typing import TYPE_CHECKING

import requests
from dotenv import find_dotenv, load_dotenv
from flask import Flask, Response, request
from upstash_redis import Redis
from upstash_redis.errors import UpstashError

if TYPE_CHECKING:
    from typing import Any, Literal

    SizeType = Literal[
        "file_url",
        "sample_url",
        "preview_url",
    ]


PREFIX = "/api/gelbooru" if __name__ != "__main__" else "/"
DEFAULT_TAGS = "+".join(
    [
        "suzuran_(arknights)",
        "rating:general",
    ]
)
API_URL = (
    "https://gelbooru.com/index.php?page=dapi&s=post&q=index&json=1&limit={}&tags={}"
)
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36"
}
CACHE_TTL = 1800


load_dotenv()
load_dotenv(find_dotenv(".env.local"))

app = Flask(__name__)
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0
formatter = logging.Formatter(
    "[%(asctime)s] [%(levelname)s] in %(module)s: %(message)s"
)
app.logger.handlers[0].setFormatter(formatter)
app.logger.setLevel(logging.INFO if not app.debug else logging.DEBUG)
app.config["KV_REST_API_URL"] = os.getenv("KV_REST_API_URL", "")
app.config["KV_REST_API_TOKEN"] = os.getenv("KV_REST_API_TOKEN", "")
app.config["GELBOORU_USER_ID"] = os.getenv("GELBOORU_USER_ID", "")
app.config["GELBOORU_API_KEY"] = os.getenv("GELBOORU_API_KEY", "")

try:
    redis_client = Redis(
        url=app.config["KV_REST_API_URL"],
        token=app.config["KV_REST_API_TOKEN"],
        allow_telemetry=False,
    )
    app.logger.info("Successfully connected to Redis.")
except UpstashError as e:
    app.logger.critical(f"Could not connect to Redis: {e}. Caching will be disabled.")
    redis_client = None

if app.config["GELBOORU_USER_ID"] and app.config["GELBOORU_API_KEY"]:
    API_URL += f"&user_id={app.config['GELBOORU_USER_ID']}&api_key={app.config['GELBOORU_API_KEY']}"


class NoImageFound(Exception):
    pass


class RequestToAPIFailed(Exception):
    pass


class NotMatchRatio(Exception):
    pass


class FailedToExtractCount(Exception):
    pass


def logger_decorator(func):
    def wrapper(*args, **kwargs):
        app.logger.debug(f"Calling {func.__name__} with args: {args}, kwargs: {kwargs}")
        result = func(*args, **kwargs)
        app.logger.debug(f"{func.__name__} returned: {result}")
        return result

    return wrapper


def hashing(value: Any) -> str:
    if isinstance(value, (bytes, str, int, float, bool)):
        norm = str(value).encode("utf-8") if not isinstance(value, bytes) else value
    elif isinstance(value, (dict, list, tuple, set, frozenset)):
        norm = json.dumps(
            sorted(value) if isinstance(value, (set, frozenset)) else value,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    else:
        raise TypeError(f"Unsupported type: {type(value)}")
    return hashlib.md5(norm).hexdigest()[:8]


def make_cache_key(func, args: tuple[Any], kwargs: dict[str, Any]) -> str:
    key_parts = [func.__name__] + [hashing(arg) for arg in args]
    key_parts += [f"{k}={hashing(v)}" for k, v in kwargs.items()]
    return ":".join(key_parts)


def cache(
    _type: type[str | int | bytes | bool | dict | list] = str, expire: int = CACHE_TTL
):
    def decorator(func):
        def wrapper(*args, **kwargs):
            if not redis_client:
                return func(*args, **kwargs)

            cache_key = make_cache_key(func, args, kwargs)
            cached_result = redis_client.get(cache_key)
            if cached_result:
                app.logger.info(f"Cache hit for {cache_key}")
                return _deserialize_cached_result(cached_result, _type)

            result = func(*args, **kwargs)
            redis_client.set(cache_key, _serialize_result(result), ex=expire)
            return result

        return wrapper

    return decorator


def _serialize_result(result: Any) -> str:
    if isinstance(result, bytes):
        return result.decode("utf-8", errors="surrogateescape")
    if isinstance(result, (dict, list)):
        return json.dumps(result)
    return str(result)


def _deserialize_cached_result(cached_result: str, _type: type) -> Any:
    if _type is bytes:
        return cached_result.encode("utf-8")
    if _type is int:
        return int(cached_result)
    if _type is bool:
        return str_to_bool(cached_result)
    if _type in {dict, list}:
        return json.loads(cached_result)
    return cached_result


def str_to_bool(value: str | bool | None) -> bool:
    if value is None:
        return False

    if isinstance(value, bool):
        return value

    return value.lower() in ("yes", "true", "t", "y", "1")


@logger_decorator
def is_fit_response_size(response: requests.Response):
    return int(response.headers.get("Content-Length", 1048576)) / 1048576


@logger_decorator
def is_fit_aspect_ratio(
    data: dict,
    image_size: str | None = None,
    aspect_ratio: float | None = None,
) -> bool:
    if not aspect_ratio:
        return True

    mapping = {
        "file_url": ("width", "height"),
        "sample_url": ("sample_width", "sample_height"),
        "preview_url": ("preview_width", "preview_height"),
    }

    width_str, height_str = mapping[image_size if image_size else "file_url"]
    width: int | None = data.get(width_str)
    height: int | None = data.get(height_str)
    if not width or not height:
        return False

    return abs((width / height) - aspect_ratio) < 0.1


def select_image(data: dict, aspect_ratio: float | None = None) -> requests.Response:
    image_sizes = dict.fromkeys(
        [
            request.args.get("prefer_size", "file_url"),
            "file_url",
            "sample_url",
            "preview_url",
        ]
    )

    post: dict | None = None
    response = None
    for post in data.get("post", []):
        if not post:
            continue

        for image_size in image_sizes:
            app.logger.info(f"Trying {image_size} for post {post.get('id')}")
            url = post.get(image_size)
            if not url or not isinstance(url, str):
                continue

            if not is_fit_aspect_ratio(
                post, image_size=image_size, aspect_ratio=aspect_ratio
            ):
                app.logger.info(f"Aspect ratio not fit for post {post.get('id')}")
                break

            response = requests.get(url, stream=True)
            if response.ok and is_fit_response_size(response) < 4:
                app.logger.info(f"Selected {image_size} for post {post.get('id')}")
                return response

        else:
            response.close() if response else None

    raise NoImageFound


# only use for api call and json return for caching. also 3hrs
@cache(dict, expire=10800)
def api_get(url: str) -> dict | None:
    response = requests.get(url, headers=HEADERS)
    response.raise_for_status()
    return response.json()


def get_image(url: str, aspect_ratio: float | None = None) -> requests.Response:
    try:
        data = api_get(url)
    except requests.RequestException as e:
        app.logger.error(f"API request failed: {e}")
        raise RequestToAPIFailed

    if not data:
        raise RequestToAPIFailed

    if not data or not data.get("post"):
        raise NoImageFound

    return select_image(data, aspect_ratio=aspect_ratio)


@cache(int)
def get_tags_count(tags: str) -> int:
    url = API_URL.format(1, tags)
    response = requests.get(url, headers=HEADERS, stream=True)

    pattern = re.compile(r"count\W+(\d+)")
    data: bytes = b""
    for chunk in response.iter_content(64):
        data += chunk
        match = pattern.search(data.decode("utf-8"))
        if match:
            return int(match.group(1))

    raise FailedToExtractCount


def get_random_image(
    tags: str,
    limit: int = 5,
    aspect_ratio: float | None = None,
) -> requests.Response | None:
    for _ in range(5):
        try:
            # pid == offset
            # so we need to divide tag_count with limit to avoid out of range
            url = (
                API_URL.format(limit, tags)
                + f"&pid={randint(0, get_tags_count(tags) // limit)}"
            )
            return get_image(url, aspect_ratio=aspect_ratio)
        except NoImageFound:
            if aspect_ratio:
                app.logger.warning(
                    "No image found with the given aspect ratio, trying again"
                )
                continue
            raise

    raise NoImageFound


@app.after_request
def add_header(r: Response):
    """
    Force cache to be disabled.
    """
    r.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    r.headers["Pragma"] = "no-cache"
    r.headers["Expires"] = "0"
    return r


def generate_response(url: str, response: requests.Response | None = None):
    if response:
        image_response = response
    else:
        try:
            image_response = requests.get(url, headers=HEADERS, stream=True)
        except requests.RequestException:
            return "Failed to get image", 500
        if not image_response.ok:
            return "Failed to get image", 500

    response_headers = {}
    for header in ("Content-Type", "Content-Length"):
        if header in image_response.headers:
            response_headers[header] = image_response.headers[header]

    def generate():
        for chunk in image_response.iter_content(2048):
            yield chunk
        image_response.close()

    return Response(generate(), headers=response_headers)


@app.route(PREFIX)
def index():
    tags = request.args.get("tags", DEFAULT_TAGS)
    limit = request.args.get("limit", 5, int)
    aspect_ratio = request.args.get("aspect_ratio", None, float)

    try:
        resp = get_random_image(tags, limit, aspect_ratio=aspect_ratio)
        if not resp:
            return "No image found", 404
    except NoImageFound:
        return "No image found", 404
    except RequestToAPIFailed:
        return "Failed to get image", 500
    except FailedToExtractCount:
        return "Failed to extract image count", 500

    if not str_to_bool(request.args.get("proxy", "false")):
        return generate_response(resp.url, response=resp)

    return "Undefined error", 500


@app.route(PREFIX + "/post")
def post():
    id = request.args.get("id")
    if not id:
        return "No id provided", 400

    try:
        resp = get_image(
            f"https://gelbooru.com/index.php?page=dapi&s=post&q=index&json=1&id={id}"
        )
        if not resp:
            return "No image found", 404
    except NoImageFound:
        return "No image found", 404
    except RequestToAPIFailed:
        return "Failed to get image", 500
    except FailedToExtractCount:
        return "Failed to extract image count", 500

    if not str_to_bool(request.args.get("proxy", "false")):
        return generate_response(resp.url, response=resp)

    return "Undefined error", 500


if __name__ == "__main__":
    app.run(host="localhost", port=8000)
