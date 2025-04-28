from __future__ import annotations

import base64
import re
from functools import cache
from random import randint
from typing import TYPE_CHECKING, Literal

import requests
from flask import Flask, Response, redirect, request, url_for

PREFIX = "/api/gelbooru" if __name__ != "__main__" else "/"
DEFAULT_TAGS = "+".join(
    [
        "suzuran_(spring_praise)_(arknights)",
        "rating:general",
    ]
)
API_URL = (
    "https://gelbooru.com/index.php?page=dapi&s=post&q=index&json=1&limit={}&tags={}"
)
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36"
}


if TYPE_CHECKING:
    SizeType = Literal[
        "file_url",
        "sample_url",
        "preview_url",
    ]


app = Flask(__name__)
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0


class NoImageFound(Exception):
    pass


class RequestToAPIFailed(Exception):
    pass


class NotMatchRatio(Exception):
    pass


class FailedToExtractCount(Exception):
    pass


def str_to_bool(value: str | bool | None) -> bool:
    if value is None:
        return False

    if isinstance(value, bool):
        return value

    return value.lower() in ("yes", "true", "t", "y", "1")


@cache
def make_url(tags: str, limit: int = 1) -> str:
    return API_URL.format(limit, tags)


def is_fit_response_size(response: requests.Response):
    return int(response.headers.get("Content-Length", 1048576)) / 1048576


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


def select_image(data: dict, aspect_ratio: float | None = None) -> str:
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
            url = post.get(image_size)
            if not url:
                continue

            response = requests.get(url, stream=True)
            if (
                response.ok
                and is_fit_aspect_ratio(
                    post, image_size=image_size, aspect_ratio=aspect_ratio
                )
                and is_fit_response_size(response) < 4
            ):
                response.close()
                return response.url

        else:
            response.close() if response else None

    raise NoImageFound


def get_image(url: str, aspect_ratio: float | None = None) -> str:
    response = requests.get(url, headers=HEADERS)
    if not response or not response.ok:
        raise RequestToAPIFailed

    data: dict[str, str] = response.json()
    if not data or not data.get("post"):
        raise NoImageFound

    return select_image(data, aspect_ratio=aspect_ratio)


@cache
def get_tags_count(tags: str) -> int:
    url = make_url(tags, limit=1)
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
) -> str:
    while True:
        try:
            url = (
                make_url(tags, limit=limit)
                + f"&pid={randint(0, get_tags_count(tags) // limit)}"
            )
            return get_image(url, aspect_ratio=aspect_ratio)
        except NoImageFound:
            if aspect_ratio:
                print("No image found with the given aspect ratio, trying again...")
                continue
            raise


@app.after_request
def add_header(r: Response):
    """
    Force cache to be disabled.
    """
    r.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    r.headers["Pragma"] = "no-cache"
    r.headers["Expires"] = "0"
    return r


def generate_response(url: str):
    headers = dict(HEADERS)
    # Forward the Range header to the upstream server
    if "Range" in request.headers:
        headers["Range"] = request.headers["Range"]

    try:
        image_response = requests.get(url, headers=headers, stream=True)
    except requests.RequestException:
        return "Failed to get image", 500

    if not image_response or not image_response.ok:
        return "Failed to get image", 500

    # Prepare response headers
    response_headers = {}

    # Copy important headers from the original response
    for header in ["Content-Type", "Content-Length", "Content-Range", "Accept-Ranges"]:
        if header in image_response.headers:
            response_headers[header] = image_response.headers[header]

    def generate():
        for chunk in image_response.iter_content(1024):
            yield chunk

    # Use the correct status code (206 for partial content)
    status_code = image_response.status_code

    return Response(generate(), headers=response_headers, status=status_code)


@app.route(PREFIX)
def index():
    tags = request.args.get("tags", DEFAULT_TAGS)
    limit = request.args.get("limit", 5, int)
    aspect_ratio = request.args.get("aspect_ratio", None, float)

    try:
        url = get_random_image(tags, limit, aspect_ratio=aspect_ratio)
        if not url:
            return "No image found", 404
    except NoImageFound:
        return "No image found", 404
    except RequestToAPIFailed:
        return "Failed to get image", 500
    except FailedToExtractCount:
        return "Failed to extract image count", 500

    if not str_to_bool(request.args.get("proxy", "false")):
        return generate_response(url)

    return redirect(
        url_for("proxy", b64url=base64.b64encode(url.encode("utf-8"))), code=302
    )


@app.route(PREFIX + "/post")
def post():
    id = request.args.get("id")
    if not id:
        return "No id provided", 400

    try:
        url = get_image(
            f"https://gelbooru.com/index.php?page=dapi&s=post&q=index&json=1&id={id}"
        )
        if not url:
            return "No image found", 404
    except NoImageFound:
        return "No image found", 404
    except RequestToAPIFailed:
        return "Failed to get image", 500
    except FailedToExtractCount:
        return "Failed to extract image count", 500

    if not str_to_bool(request.args.get("proxy", "false")):
        return generate_response(url)

    return redirect(
        url_for("proxy", b64url=base64.b64encode(url.encode("utf-8"))), code=302
    )


@app.route(PREFIX + "/proxy")
def proxy():
    b64url = request.args.get("b64url")
    if not b64url:
        return "No b64url provided", 400

    url = base64.b64decode(b64url).decode("utf-8")
    if not url:
        return "Invalid b64url", 400

    # return generate_response(lambda: requests.get(url, headers=HEADERS, stream=True))

    try:
        image_response = requests.get(url, stream=True)
    except requests.RequestException:
        return "Failed to get image", 500

    if not image_response or not image_response.ok:
        return "Failed to get image", 500

    return generate_response(url)


if __name__ == "__main__":
    app.run(host="localhost", port=8000)
