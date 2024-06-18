import os

from flask import Flask, render_template

PREFIX = "/"
BASEDIR = os.path.dirname(os.path.abspath(__file__))

app = Flask(
    __name__,
    template_folder=os.path.join(BASEDIR, *[os.path.pardir, "templates"]),
    static_folder=os.path.join(BASEDIR, *[os.path.pardir, "static"]),
)


@app.route(PREFIX)
def index():
    return render_template("index.html")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)
