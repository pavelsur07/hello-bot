"""Synthetic HTTP responses shared by tests; no real transport is used."""

import json


class FakeResponse:
    def __init__(self, body: object):
        self.body = json.dumps(body).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self):
        return self.body
