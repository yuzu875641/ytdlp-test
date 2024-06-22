function humanFileSize(bytes, si = false, dp = 1) {
  const thresh = si ? 1000 : 1024;

  if (Math.abs(bytes) < thresh) {
    return bytes + ' B';
  }

  const units = si
    ? ['kB', 'MB', 'GB', 'TB', 'PB', 'EB', 'ZB', 'YB']
    : ['KiB', 'MiB', 'GiB', 'TiB', 'PiB', 'EiB', 'ZiB', 'YiB'];
  let u = -1;
  const r = 10 ** dp;

  do {
    bytes /= thresh;
    ++u;
  } while (Math.round(Math.abs(bytes) * r) / r >= thresh && u < units.length - 1);


  return bytes.toFixed(dp) + ' ' + units[u];
}

function isValidHttpUrl(string) {
  let url;

  try {
    url = new URL(string);
  } catch (_) {
    return false;
  }

  return url.protocol === "http:" || url.protocol === "https:";
}

function resetDownloadText(setOriginal = true) {
  const downloadText = document.getElementById("download-text")
  downloadText.classList.remove("red")
  if (setOriginal) {
    downloadText.innerHTML = "download"
  }
}

function animateDownloadText(afterText = "download", animation = true) {
  const downloadText = document.getElementById("download-text")
  if (animation) {
    downloadText.classList.add("no-opacity")
  }
  setTimeout(() => {
    resetDownloadText(false)
    downloadText.innerHTML = afterText
    downloadText.classList.remove("no-opacity")
  }, 200)
}

function animateErrorText(afterText) {
  const downloadText = document.getElementById("download-text")
  resetDownloadText(false)
  downloadText.classList.add("no-opacity")
  setTimeout(() => {
    downloadText.innerHTML = afterText
    downloadText.classList.add("red")
    downloadText.classList.remove("no-opacity")
  }, 200)
}

function submit(url) {
  if (!isValidHttpUrl(url)) {
    return
  }
  animateDownloadText("...")

  fetch("/api/ytdl/check", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      query: url,
      type: document.getElementsByClassName("av-wrapper")[0].getAttribute("data-value"),
      has_ffmpeg: window.WP_ffmpeg !== undefined && window.WP_ffmpeg.loaded
    }),
  }).then((response) => {
    if (!response.ok) {
      throw new Error(response.statusText);
    }
    return response.json();
  })
    .then(async (data) => {
      animateDownloadText("downloading...");
      if (data.needs_ffmpeg == true) {
        if (!window.WP_ffmpeg.loaded) {
          animateErrorText("ffmpeg not loaded");
          return;
        }

        const params = {
          filename: data.title,
        };
        debugger;
        for (const format of data.requested_formats) {
          const fileData = format.is_part ? await partsDownload(format) : await fetchFile(`/api/ytdl/download?video_id=${format.video_id}`);
          params[`${format.type}Data`] = fileData;
          params[`${format.type}Ext`] = format.ext;
          params[`${format.type}Title`] = format.format_id;
        }
        await ffmpegDownload(params);
        animateDownloadText("download");
        return;
      }

      if (data.is_part == true) {
        return partsDownload(data)
          .then((data) => {
            saveAs(data, data.name);
            animateDownloadText("download");
          })
          .catch(() => {
            animateErrorText("invalid url");
          });
      }
      download(data);
    })
}

function saveAs(blob, filename) {
  const url = window.URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.style.display = "none";
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  setTimeout(() => {
    document.body.removeChild(a);
    window.URL.revokeObjectURL(url);
  }, 100);
}

async function parts(bufferList, url, video_id, filesize_approx, range_start) {
  const postResp = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      video_id: video_id,
      range_start: range_start,
      filesize_approx: filesize_approx
    }),
  })

  const postData = await postResp.json()
  if (postData.status == "finished") {
    return
  }

  const getResp = await fetch(postData.url)
  if (getResp.status == 416) {
    return
  }

  const contentLength = getResp.headers.get("Content-Length")
  const new_range_start = Number(range_start) + Number(contentLength)

  animateDownloadText(`downloading... ${humanFileSize(new_range_start)}/${humanFileSize(filesize_approx)}`, false)

  arrayBuffer = await getResp.arrayBuffer()
  bufferList.push(arrayBuffer)
  await parts(bufferList, url, video_id, filesize_approx, new_range_start)
}

async function ffmpegDownload({ filename, videoData, videoTitle, videoExt, audioData, audioTitle, audioExt }) {
  debugger;
  const videoName = videoTitle + "." + videoExt
  const audioName = audioTitle + "." + audioExt

  if (videoData.constructor.name == "Blob") {
    videoData = new Uint8Array(await videoData.arrayBuffer())
  }
  if (audioData.constructor.name == "Blob") {
    audioData = new Uint8Array(await audioData.arrayBuffer())
  }

  animateDownloadText(`ffmpeg-ing...`)
  const ffmpeg = window.WP_ffmpeg;
  await ffmpeg.writeFile(
    videoName,
    videoData
  );
  await ffmpeg.writeFile(
    audioName,
    audioData
  );
  await ffmpeg.exec(
    [
      "-i",
      videoName,
      "-i",
      audioName,
      "-c:v",
      "copy",
      "-c:a",
      "copy",
      "output.mp4"
    ],
  );
  const data = await ffmpeg.readFile('output.mp4');
  const blob = new Blob([data], { type: `video/${videoExt}` });
  saveAs(blob, filename);
  animateDownloadText("download")
}

async function partsDownload(data) {
  const url = data.url || "/api/ytdl/part-download";
  const bufferList = [];
  const video_id = data.video_id;
  const filesize_approx = data.filesize_approx;

  await parts(bufferList, url, video_id, filesize_approx, 0);
  const blob = new Blob(bufferList, { type: "application/octet-stream" });
  return blob;
}

function download(data) {
  const a = document.createElement("a");
  a.href = `/api/ytdl/download?video_id=${data.video_id}`;
  a.download = data.title + "." + data.ext;
  a.click();
  setTimeout(() => {
    animateDownloadText()
  }, 5000)
}

function checkInput(input) {
  const downloadBtn = document.getElementById("download-button")
  if (input.value == "") {
    downloadBtn.classList.remove("disabled")
    resetDownloadText()
    return
  }

  if (isValidHttpUrl(input.value)) {
    downloadBtn.classList.remove("disabled")
  } else {
    downloadBtn.classList.add("disabled")
  }
}

function videoSwitch() {
  document.getElementsByClassName("av-wrapper")[0].setAttribute("data-value", "video")
  document.getElementById("video-switch").classList.add("selected")
  document.getElementById("audio-switch").classList.remove("selected")
}

function audioSwitch() {
  document.getElementsByClassName("av-wrapper")[0].setAttribute("data-value", "audio")
  document.getElementById("audio-switch").classList.add("selected")
  document.getElementById("video-switch").classList.remove("selected")
}