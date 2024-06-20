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

async function submit(url) {
  if (!isValidHttpUrl(url)) {
    return
  }
  animateDownloadText("...")

  await fetch("/api/ytdl/check", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      query: url,
      type: document.getElementsByClassName("av-wrapper")[0].getAttribute("data-value")
    }),
  }).then((response) => {
    if (!response.ok) {
      throw new Error(response.statusText);
    }
    return response.json();
  })
    .then((data) => {
      // console.log("Success:", data);
      animateDownloadText("downloading...");
      if (data.is_part == true) {
        return downloadParts(data);
      }
      download(data);
    })
    .catch(() => {
      animateErrorText("invalid url");
    });
}

function saveAs(arrayBuffers, filename) {
  const blob = new Blob(arrayBuffers, { type: "application/octet-stream" });
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
  const contentLength = getResp.headers.get("Content-Length")
  const new_range_start = Number(range_start) + Number(contentLength)

  animateDownloadText(`downloading... ${humanFileSize(new_range_start)}/${humanFileSize(filesize_approx)}`, false)

  arrayBuffer = await getResp.arrayBuffer()
  bufferList.push(arrayBuffer)
  await parts(bufferList, url, video_id, filesize_approx, new_range_start)
}

function downloadParts(data) {
  const url = data.url
  const bufferList = []
  const video_id = data.video_id
  const filesize_approx = data.filesize_approx
  parts(bufferList, url, video_id, filesize_approx, 0)
    .then(() => {
      saveAs(bufferList, data.title + "." + data.ext);
      animateDownloadText();
    })
    .catch((error) => {
      animateErrorText("invalid url");
    });
}

function download(data) {
  const a = document.createElement("a");
  a.href = `/api/ytdl/download?video_id=${data.video_id}&filesize_approx=${data.filesize_approx}`;
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