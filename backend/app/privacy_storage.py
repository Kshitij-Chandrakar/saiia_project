"""Private account-owned streaming Storage adapter; no public/signed URLs."""

import json
from urllib.parse import urlsplit

import requests

from app.privacy_content import ContentBlocked, owned_key


class PrivateStorage:
    def __init__(self, url, key, *, local_rehearsal=False):
        parsed = urlsplit(url)
        if (
            parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or (
                parsed.scheme != "https"
                and not (
                    local_rehearsal
                    and parsed.scheme == "http"
                    and parsed.hostname in {"127.0.0.1", "localhost", "storage"}
                )
            )
        ):
            raise ContentBlocked("storage_configuration_invalid")
        self.url, self.key = url.rstrip("/"), key
        self.http = requests.Session()
        self.http.trust_env = False

    def request(self, method, bucket, key=None, **kwargs):
        if bucket not in {"resumes", "exports"}:
            raise ContentBlocked("storage_scope_denied")
        if key is not None:
            owned_key(key.split("/")[0], key)
        return self.http.request(
            method,
            self.url + "/object/" + bucket + ("/" + key if key else ""),
            headers={
                "Authorization": "Bearer " + self.key,
                "apikey": self.key,
                "Content-Type": "application/zip"
                if "data" in kwargs
                else "application/json",
            },
            allow_redirects=False,
            timeout=(3, 10),
            **kwargs,
        )

    def stat(self, bucket, key):
        with self.request("GET", bucket, key, stream=True) as response:
            if response.status_code == 200:
                version = response.headers.get("ETag")
                if not version:
                    raise ContentBlocked("storage_version_missing")
                return version
            if response.status_code in (401, 403):
                raise PermissionError()
            if response.status_code in (400, 404):
                body = bytearray()
                for chunk in response.iter_content(4096):
                    if len(body) + len(chunk) > 65536:
                        raise ContentBlocked("storage_unavailable")
                    body.extend(chunk)
                error = json.loads(body)
                if str(error.get("statusCode")) == "404" or error.get("error") in (
                    "not_found",
                    "Not Found",
                ):
                    return None
            raise ContentBlocked("storage_unavailable")

    def read(self, bucket, key, version):
        with self.request("GET", bucket, key, stream=True) as response:
            if response.status_code in (401, 403):
                raise PermissionError()
            if response.status_code != 200 or response.headers.get("ETag") != version:
                raise ContentBlocked("storage_changed_or_unavailable")
            yield from response.iter_content(65536)

    def put(self, bucket, key, source):
        with self.request("POST", bucket, key, data=source) as response:
            if response.status_code in (401, 403):
                raise PermissionError()
            if response.status_code != 200:
                raise ContentBlocked("storage_write_unverified")

    def remove(self, bucket, key):
        owned_key(key.split("/")[0], key)
        with self.request("DELETE", bucket, json={"prefixes": [key]}) as response:
            if response.status_code in (401, 403):
                raise PermissionError()
            if response.status_code != 200:
                raise ContentBlocked("storage_removal_unverified")
