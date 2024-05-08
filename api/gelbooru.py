from random import randint
import requests
from flask import Flask, Response

PREFIX = "/api/gelbooru"
TAGS = ["suzuran_(spring_praise)_(arknights)", "-rating:explicit"]

app = Flask(__name__)
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0


class EmptyResponse(Exception):
    pass


def str_to_bool(value: str | bool | None) -> bool:
    if value is None:
        return False

    if isinstance(value, bool):
        return value

    return value.lower() in ("yes", "true", "t", "y", "1")


def calculate_size(response: requests.Response):
    return int(response.headers.get("Content-Length", 1048576)) / 1048576


def select_image(data: dict) -> requests.Response | None:
    post = data.get("post", [None])[0]
    if not post:
        return None

    urls = [post.get("file_url"), post.get("sample_url")]
    for url in filter(None, urls):
        response = requests.get(url, stream=True)
        if response.ok and calculate_size(response) < 4:
            return response


def get_tags_count(tags: list[str]) -> int:
    url = "https://gelbooru.com/index.php"
    params = {
        "page": "dapi",
        "s": "post",
        "q": "index",
        "json": 1,
        "tags": "+".join(tags),
        "limit": 1,
    }

    response = requests.get(
        url, params="&".join("%s=%s" % (k, v) for k, v in params.items())
    )
    response.raise_for_status()

    data = response.json()
    return data["@attributes"]["count"]


def get_random_image(tags: list[str]) -> requests.Response | None:
    api_url = "https://gelbooru.com/index.php"
    api_params = {
        "page": "dapi",
        "s": "post",
        "q": "index",
        "json": 1,
        "tags": "+".join(tags),
        "limit": 1,
        "pid": randint(1, get_tags_count(tags)),
    }

    response = requests.get(
        api_url, params="&".join("%s=%s" % (k, v) for k, v in api_params.items())
    )
    if not response or not response.ok:
        raise EmptyResponse()

    data = response.json()
    if not data or not data.get("post"):
        raise EmptyResponse()

    return select_image(data)


@app.after_request
def add_header(r):
    """
    Add headers to both force latest IE rendering engine or Chrome Frame,
    and also to cache the rendered page for 10 minutes.
    """
    r.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    r.headers["Pragma"] = "no-cache"
    r.headers["Expires"] = "0"
    r.headers["Cache-Control"] = "public, max-age=0"
    return r


@app.route(PREFIX)
def index():
    try:
        image_response = get_random_image(TAGS)
    except EmptyResponse:
        return "No image found", 404

    if not image_response:
        return "No image found", 404

    def generate_response():
        for chunk in image_response.iter_content(1024):
            yield chunk

    content_type = image_response.headers.get("Content-Type")
    return Response(generate_response(), content_type=content_type)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
