from __future__ import annotations

import base64
from random import randint
import re
from typing import Literal, TYPE_CHECKING
import requests
from flask import Flask, Response, redirect, request, url_for

PREFIX = "/api/gelbooru" if __name__ != "__main__" else "/"
TAGS = ["suzuran_(spring_praise)_(arknights)", "rating:general"]
API_URL = (
    "https://gelbooru.com/index.php?page=dapi&s=post&q=index&json=1&limit={}&tags={}"
)
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36"
}
app = Flask(__name__)
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0

if TYPE_CHECKING:
    SizeType = Literal[
        "file_url",
        "sample_url",
        "preview_url",
    ]


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


def make_url(tags: list[str] | str, limit: int = 1) -> str:
    if isinstance(tags, str):
        tags = [tags]
    return API_URL.format(limit, "+".join(tags))


def calculate_size(response: requests.Response):
    return int(response.headers.get("Content-Length", 1048576)) / 1048576


def select_image(data: dict) -> str:
    sizes = dict.fromkeys(
        [
            request.args.get("prefer_size", "file_url"),
            "file_url",
            "sample_url",
            "preview_url",
        ]
    )

    post: dict | None
    for post in data.get("post", []):
        if not post:
            continue

        for size in sizes:
            url = post.get(size)
            if not url:
                continue
            response = requests.get(url, stream=True)
            if response.ok and calculate_size(response) < 4:
                response.close()
                return response.url
        else:
            response.close()

    raise NoImageFound


def get_image(url: str) -> str:
    response = requests.get(url, headers=HEADERS)
    if not response or not response.ok:
        raise RequestToAPIFailed

    data: dict[str, str] = response.json()
    if not data or not data.get("post"):
        raise NoImageFound

    return select_image(data)


def get_tags_count(tags: list[str] | str) -> int:
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


def get_random_image(tags: list[str] | str, limit: int = 5) -> str:
    url = (
        make_url(tags, limit=limit)
        + f"&pid={randint(0, get_tags_count(tags) // limit)}"
    )
    return get_image(url)


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
    tags = request.args.get("tags", TAGS)
    limit = request.args.get("limit", 5, int)
    try:
        url = get_random_image(tags, limit)
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
