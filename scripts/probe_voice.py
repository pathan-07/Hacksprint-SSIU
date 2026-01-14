import urllib.error
import urllib.request


def main() -> None:
    url = "http://127.0.0.1:8000/demo/voice?shop_phone=%2B919999999999"
    boundary = "----probe"
    pre = (
        f"--{boundary}\r\n"
        "Content-Disposition: form-data; name=\"file\"; filename=\"a.webm\"\r\n"
        "Content-Type: audio/webm\r\n\r\n"
    )
    post = f"\r\n--{boundary}--\r\n"

    body = pre.encode("utf-8") + b"abc123" + post.encode("utf-8")

    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")

    try:
        resp = urllib.request.urlopen(req)
        print(resp.status)
        print(resp.read().decode("utf-8", "ignore"))
    except urllib.error.HTTPError as e:
        print(e.code)
        print(e.read().decode("utf-8", "ignore"))


if __name__ == "__main__":
    main()
