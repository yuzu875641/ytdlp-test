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

function animateDownloadText(afterText) {
  const downloadText = document.getElementById("download-text")
  downloadText.classList.add("no-opacity")
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
    body: JSON.stringify({ query: url }),
  }).then((response) => {
    if (!response.ok) {
      throw new Error(response.statusText);
    }
    return response.json();
  })
    .then((data) => {
      console.log("Success:", data);
      download(data)
    })
    .catch((error) => {
      animateErrorText("invalid url")
    });
}

function download(data) {
  a = document.createElement("a");
  a.href = `/api/ytdl/download?video_id=${data.video_id}&chunk_size=${data.chunk_size}`;
  a.download = data.title + "." + data.ext;
  a.click();
}

function checkInput(input) {
  downloadBtn = document.getElementById("download-button")
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