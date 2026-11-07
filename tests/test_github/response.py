"""Scoped in-memory JSON response for internal REST controls."""

import json


class JsonResponse:
    def __init__(self, value):
        self.value = value

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass

    def read(self, limit):
        return json.dumps(self.value).encode()[:limit]
