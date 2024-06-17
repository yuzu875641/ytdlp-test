import requests

# js = requests.post(
#     "http://localhost:8000/api/ytdl/query",
#     json={
#         "query": "https://music.youtube.com/watch?v=osFSvL8-cuk",
#     },
# ).json()

# origin_keys = [k for k in js["formats"][0].keys()]
# for format in js["formats"]:
#     for k in format.keys():
#         if k not in origin_keys:
#             print(f"key diff: {k}")
#             origin_keys.append(k)

# for i in sorted(origin_keys):
#     print("".join(i.title().split("_")))

r = requests.get(
    "https://rr4---sn-8pxuuxa-nbozz.googlevideo.com/videoplayback?expire=1718662175&ei=v19wZq37BsGbvcAP9LKr-AY&ip=116.110.41.152&id=o-AN-SwYP8MQYKtw8yIUOhO-_BGkF8SH_wRCMtYg6VcC7u&itag=140&source=youtube&requiressl=yes&xpc=EgVo2aDSNQ%3D%3D&mh=Px&mm=31%2C29&mn=sn-8pxuuxa-nbozz%2Csn-8pxuuxa-nbo6l&ms=au%2Crdu&mv=m&mvi=4&pl=22&gcr=vn&initcwndbps=1121250&vprv=1&svpuc=1&mime=audio%2Fmp4&rqh=1&gir=yes&clen=3557781&dur=219.718&lmt=1681983237490052&mt=1718640303&fvip=8&keepalive=yes&c=IOS&txp=4432434&sparams=expire%2Cei%2Cip%2Cid%2Citag%2Csource%2Crequiressl%2Cxpc%2Cgcr%2Cvprv%2Csvpuc%2Cmime%2Crqh%2Cgir%2Cclen%2Cdur%2Clmt&sig=AJfQdSswRAIgRcWeoSMwJJtqwMB5X6V-W_zaV32k7zOSttM97vVLZlMCIA8GLl9TLgCQ3ZqcP4VNcau1AbOsMhT_o8m2kmcW6YdH&lsparams=mh%2Cmm%2Cmn%2Cms%2Cmv%2Cmvi%2Cpl%2Cinitcwndbps&lsig=AHlkHjAwRQIhAPfbyLEwdvE0d1OD62oUOhbyqyomdVN1LWnC2PxHxFQfAiA_HgmwpnF-c4pIW4rSN2SF1FZbDAyAuhL54zXRjFcRUA%3D%3D",
    headers={
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        "Range": "bytes=0-",
    },
    stream=True,
)
