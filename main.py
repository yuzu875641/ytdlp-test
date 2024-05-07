from yt_dlp import YoutubeDL
from fastapi import FastAPI

app = FastAPI()
ytdl = YoutubeDL()


@app.get("/")
async def index():
    return {"message": "Hello World"}


@app.get("/hello")
async def hello():
    return {"message": "Hello World"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app)
