from random import randint
import requests
from flask import Flask, Response

PREFIX = "/api/gelbooru"
TAGS = ["suzuran_(spring_praise)_(arknights)", "-rating:explicit"]

app = Flask(__name__)
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0


class EmptyResponse(Exception):
    pass


def str_to_bool(s: str | bool | None) -> bool:
    if s is None:
        return False

    if isinstance(s, bool):
        return s

    if s.lower() in ("yes", "true", "t", "y", "1"):
        return True

    return False


def get_random(tags: list[str]):
    url = f"https://gelbooru.com/index.php?page=dapi&s=post&q=index&json=1&tags={'+'.join(tags)}&limit=1"

    # get number of image and then random it to get the url
    ret = requests.get(url)
    if ret is None:
        raise EmptyResponse()
    ret_json = ret.json()

    try:
        count: int = ret_json["@attributes"]["count"]
    except KeyError:
        raise EmptyResponse()

    ret = requests.get(url + f"&pid={randint(1, count)}")
    if not ret or not ret.ok:
        raise EmptyResponse()

    ret_json = ret.json()
    if posts := ret_json.get("post"):
        posts = posts[0]
        if url := posts.get("file_url"):
            return url

        if url := posts.get("sample_url"):
            return url

    raise EmptyResponse()


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
    while True:
        try:
            url = get_random(TAGS)
        except EmptyResponse:
            return "No image found", 404

        ret = requests.get(url, stream=True)
        content_lenght = ret.headers.get("Content-Length", 1048576)
        size = int(content_lenght) / 1048576 if content_lenght else -1
        if size > 0 and size < 6:
            break

    def iter_content():
        for chunk in ret.iter_content(1024):
            yield chunk

    return Response(iter_content(), content_type=ret.headers.get("Content-Type"))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
