import { FFmpeg } from '@ffmpeg/ffmpeg';
import { fetchFile, toBlobURL } from '@ffmpeg/util';
import AWN from "awesome-notifications"

import _ from 'lodash';

window.onload = function () {
    window.fetchFile = fetchFile;
    window.WP_ffmpeg = new FFmpeg();
    window.WP_notifier = new AWN({
        labels: {
            async: "",
            success: ""
        }
    });
    (async () => {
        const baseURL = 'https://unpkg.com/@ffmpeg/core@0.12.6/dist/umd'
        window.WP_ffmpeg.on('log', ({ message }) => {
            console.log(message);
        });
        // toBlobURL is used to bypass CORS issue, urls with the same
        // domain can be used directly.
        await window.WP_notifier.async(
            window.WP_ffmpeg.load({
                coreURL: await toBlobURL(`${baseURL}/ffmpeg-core.js`, 'text/javascript'),
                wasmURL: await toBlobURL(`${baseURL}/ffmpeg-core.wasm`, 'application/wasm'),
            }),
            "FFmpeg loaded",
            err => window.WP_notifier.alert(err.message),
            "FFmpeg loading..."
        );
    })()
        .then(async () => {
            const version = await window.WP_ffmpeg.exec(["--help"])
            console.log(version)
        })
        .catch(console.log);
}