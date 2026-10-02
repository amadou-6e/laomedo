"""Synthetic writable stage that repeatedly attempts an external effect."""

import os
import time
from urllib import error, request


TOKEN = os.environ["CANARY_GRANT"]
URL = "http://canary:8099/write"
while True:
    req = request.Request(URL, data=b"synthetic", method="POST",
                          headers={"X-Test-Grant": TOKEN})
    try:
        request.urlopen(req, timeout=2).close()
    except (error.URLError, TimeoutError, OSError):
        pass
    time.sleep(0.2)
