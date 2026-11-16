"""Private local acceptance driver; prints only bounded public observations."""

import http.cookiejar
import json
from pathlib import Path
import urllib.request

workspace = Path("C:/CodeWorkspace/laomedo")
metadata = json.loads((workspace / ".tools/assistant-282-live.json").read_text())
base = metadata["base"]
cookies = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(
    urllib.request.HTTPCookieProcessor(cookies), urllib.request.ProxyHandler({})
)
login = json.load(opener.open(base + "/api/v1/auto_login", timeout=20))
token = login["access_token"]
headers = {
    "Authorization": "Bearer " + token,
    "Origin": base,
    "Content-Type": "application/json",
}
(Path(metadata["state"]) / "acceptance-session.json").write_text(
    json.dumps({"token": token}), encoding="utf-8"
)
for path in ("/status", "/models"):
    try:
        request = urllib.request.Request(
            base + "/api/v1/laomedo/assistant" + path, headers=headers
        )
        result = json.load(opener.open(request, timeout=180))
        print(json.dumps({"path": path, "result": result}), flush=True)
    except urllib.error.HTTPError as error:
        print(
            json.dumps(
                {"path": path, "status": error.code, "result": json.load(error)}
            ),
            flush=True,
        )
