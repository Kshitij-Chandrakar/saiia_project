"""Approved three-object/two-email acceptance. No retries or overwrites."""

import argparse
import hashlib
import io
import json
import os
from pathlib import Path
from types import SimpleNamespace

import requests
from c12_email_acceptance import BoundedSession, execute
from PIL import Image

ORIGIN = "https://rbmxfazjbldmkomdpyzl.supabase.co"
BUCKET = "email-assets"
PUBLIC = ORIGIN + "/storage/v1/object/public/" + BUCKET
ASSETS = (
    (
        "payment-success.jpg",
        "payment-success-20261027-v1.jpg",
        "image/jpeg",
        (1080, 540),
        "fc0281dcb9f24820b27437cbdfc7e4faabf9d901becdae3a92c5a9fac0301700",
    ),
    (
        "renewal-success.jpg",
        "renewal-success-20261027-v1.jpg",
        "image/jpeg",
        (1080, 540),
        "6d68e5e934940dd81ee2085583a3a3c4d64fdca1deb1b706879d9f8c767fabab",
    ),
    (
        "mascot.png",
        "mascot-20261027-v1.png",
        "image/png",
        (120, 80),
        "cbec3e0d352464f2d36f6b9244f955897751c39c313d50205a1ee29e12b93427",
    ),
)


def storage_credentials():
    values = {}
    for line in Path(".env").read_text(encoding="utf-8-sig").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            name, value = line.split("=", 1)
            if name.strip() in ("SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY"):
                values[name.strip()] = value.strip().strip('"').strip("'")
    if values.get("SUPABASE_URL", "").rstrip("/") != ORIGIN:
        raise ValueError("Storage project mismatch")
    if not values.get("SUPABASE_SERVICE_ROLE_KEY"):
        raise ValueError("SUPABASE_SERVICE_ROLE_KEY unavailable")
    return values


class Publication:
    def __init__(self, journal, session, key, *, initialize=True):
        self.journal, self.session, self.key = journal, session, key
        self.session.trust_env = False
        if not initialize:
            return
        journal.state.update(
            storage_read_attempts=0,
            upload_attempts=0,
            maximum_storage_reads=12,
            maximum_uploads=3,
            storage_observations=[],
            published_assets=[],
        )
        journal.save()

    def call(self, method, path, *, upload=False, public=False, **kwargs):
        allowed = {
            ("GET", "/storage/v1/bucket/email-assets"),
            ("POST", "/storage/v1/object/list/email-assets"),
        }
        allowed |= {
            ("GET", "/storage/v1/object/public/email-assets/" + item[1])
            for item in ASSETS
        }
        if upload:
            if (method, path) not in {
                ("POST", "/storage/v1/object/email-assets/" + item[1])
                for item in ASSETS
            }:
                raise ValueError("Unapproved upload target")
        elif (method, path) not in allowed:
            raise ValueError("Unapproved Storage read")
        self.journal.start_window()
        counter, limit = (
            ("upload_attempts", 3) if upload else ("storage_read_attempts", 12)
        )
        if self.journal.state[counter] >= limit:
            raise ValueError("Storage operation limit reached")
        self.journal.state[counter] += 1
        record = {
            "method": method,
            "path": path,
            "kind": counter,
            "outcome": "reserved",
        }
        self.journal.state["storage_observations"].append(record)
        self.journal.save()
        headers = kwargs.pop("headers", {})
        headers |= {"Accept-Encoding": "identity", "Connection": "close"}
        if not public:
            headers |= {"apikey": self.key, "Authorization": "Bearer " + self.key}
        try:
            result = self.session.request(
                method,
                ORIGIN + path,
                headers=headers,
                timeout=(3, 10),
                allow_redirects=False,
                **kwargs,
            )
        except requests.RequestException:
            record["outcome"] = "unknown_transport_result"
            self.journal.save()
            raise
        record.update(outcome="response_received", http_status=result.status_code)
        record["transfer"] = {
            name: result.headers[name]
            for name in (
                "content-length",
                "content-type",
                "content-encoding",
                "transfer-encoding",
            )
            if name in result.headers
        }
        self.journal.save()
        return result

    def publish(self):
        bucket = self.call("GET", "/storage/v1/bucket/email-assets")
        if (
            bucket.status_code != 200
            or bucket.json().get("public") is not True
            or bucket.json().get("id") != BUCKET
        ):
            raise ValueError("Expected public email-assets bucket unavailable")
        listing = self.call(
            "POST",
            "/storage/v1/object/list/email-assets",
            json={
                "prefix": "",
                "limit": 1000,
                "offset": 0,
                "sortBy": {"column": "name", "order": "asc"},
            },
        )
        if (
            listing.status_code != 200
            or not isinstance(listing.json(), list)
            or len(listing.json()) >= 1000
        ):
            raise ValueError("Unable to establish existing object inventory")
        names = {row["name"] for row in listing.json()}
        self.journal.state["existing_objects"] = sorted(names)
        self.journal.save()
        if names.intersection(item[1] for item in ASSETS):
            raise ValueError("Versioned target already exists; no overwrite")
        self.publish_remaining()

    def publish_remaining(self):
        for source, name, mime, dimensions, digest in ASSETS:
            if any(
                asset["object"] == name and asset["verified"]
                for asset in self.journal.state["published_assets"]
            ):
                continue
            data = (Path("frontend/public/email-assets/billing") / source).read_bytes()
            if hashlib.sha256(data).hexdigest() != digest:
                raise ValueError("Local asset hash changed")
            self.journal.state["stage"] = "upload:" + name
            self.journal.save()
            try:
                response = self.call(
                    "POST",
                    "/storage/v1/object/email-assets/" + name,
                    upload=True,
                    data=data,
                    headers={
                        "Content-Type": mime,
                        "Cache-Control": "max-age=31536000",
                        "x-upsert": "false",
                    },
                )
                if response.status_code not in (200, 201):
                    raise ValueError("Upload rejected; inspect recorded HTTP status")
            except requests.RequestException:
                # One bounded read may establish whether an uncertain upload
                # created the exact intended object. Never retry creation.
                pass
            self.verify((source, name, mime, dimensions, digest))

    def verify(self, asset):
        source, name, mime, dimensions, digest = asset
        data = (Path("frontend/public/email-assets/billing") / source).read_bytes()
        self.journal.state["stage"] = "verify:" + name
        self.journal.save()
        verified = self.call(
            "GET", "/storage/v1/object/public/email-assets/" + name, public=True
        )
        if (
            verified.status_code != 200
            or verified.headers.get("content-type", "").split(";")[0].lower() != mime
            or hashlib.sha256(verified.content).hexdigest() != digest
        ):
            raise ValueError("Published asset verification failed")
        with Image.open(io.BytesIO(verified.content)) as image:
            if image.size != dimensions:
                raise ValueError("Published dimensions mismatch")
        self.journal.state["published_assets"].append(
            {
                "object": name,
                "url": PUBLIC + "/" + name,
                "sha256": digest,
                "width": dimensions[0],
                "height": dimensions[1],
                "bytes": len(data),
                "content_type": mime,
                "verified": True,
                "retain": True,
            }
        )
        self.journal.save()


def existing_journal():
    journal = object.__new__(BoundedSession)
    journal.path = Path("tmp/c12-email-redesign-01/execution.json")
    journal.state = json.loads(journal.path.read_text(encoding="utf-8"))
    journal.sender = "billing@intervucopilot.in"
    journal.recipient = "acceptance-recipient@example.invalid"
    journal.transport = requests.Session()
    journal.transport.trust_env = False
    journal.start_window()  # Existing clock only; expired windows fail closed.
    if (
        journal.state["attempts"] != 0
        or journal.state["upload_attempts"] > 3
        or journal.state["storage_read_attempts"] > 12
    ):
        raise ValueError("Recovery state outside approved scope")
    return journal


def reconcile_publication():
    journal = existing_journal()
    backup = journal.path.with_name("execution-at-transfer-stop.json")
    with backup.open("x", encoding="utf-8") as stream:
        stream.write(journal.path.read_text(encoding="utf-8"))
    values = storage_credentials()
    storage = requests.Session()
    publication = Publication(
        journal, storage, values["SUPABASE_SERVICE_ROLE_KEY"], initialize=False
    )
    try:
        journal.state["recovery"] = (
            "Engineer-directed single verification read with identity encoding/closed connection; original deadline and counters retained"
        )
        journal.save()
        publication.verify(ASSETS[0])
        publication.publish_remaining()
        journal.state["stage"] = "all_assets_verified_awaiting_masked_email_key"
    finally:
        publication.key = ""
        values.clear()
        storage.close()
        journal.transport.close()
        journal.state["status"] = "stopped"
        journal.save()


def continue_verified_email(pg_bin):
    journal = existing_journal()
    if {
        asset["object"]
        for asset in journal.state["published_assets"]
        if asset["verified"]
    } != {asset[1] for asset in ASSETS}:
        raise ValueError("All three verified assets required")
    os.environ["EMAIL_ASSET_BASE_URL"] = PUBLIC
    os.environ.pop("EMAIL_WEBSITE_ORIGIN", None)
    try:
        execute(
            SimpleNamespace(
                execute=True,
                sender_domain_verified=True,
                sender=journal.sender,
                recipient=journal.recipient,
                evidence=str(journal.path.parent),
                pg_bin=pg_bin,
            ),
            journal=journal,
        )
        journal.state["stage"] = "finished"
    finally:
        for name in ("RESEND_API_KEY", "EMAIL_ASSET_BASE_URL", "EMAIL_WEBSITE_ORIGIN"):
            os.environ.pop(name, None)
        journal.transport.close()
        journal.state["status"] = "stopped"
        journal.save()


def run(pg_bin):
    credential = os.environ.pop("RESEND_API_KEY", "")
    if not credential:
        raise ValueError("RESEND_API_KEY unavailable")
    for source, _, _, _, digest in ASSETS:
        if (
            hashlib.sha256(
                (Path("frontend/public/email-assets/billing") / source).read_bytes()
            ).hexdigest()
            != digest
        ):
            raise ValueError("Pinned local asset changed; no external activity")
    directory = Path("tmp/c12-email-redesign-01")
    transport = requests.Session()
    transport.trust_env = False
    journal = BoundedSession(
        directory,
        "billing@intervucopilot.in",
        "acceptance-recipient@example.invalid",
        transport,
    )
    storage = requests.Session()
    values = storage_credentials()
    publication = Publication(journal, storage, values["SUPABASE_SERVICE_ROLE_KEY"])
    try:
        publication.publish()
        assert len(journal.state["published_assets"]) == 3
        storage.close()
        publication.key = ""
        values.clear()
        os.environ["EMAIL_ASSET_BASE_URL"] = PUBLIC
        os.environ.pop("EMAIL_WEBSITE_ORIGIN", None)
        os.environ["RESEND_API_KEY"] = credential
        journal.state["stage"] = "verified_assets_then_email_acceptance"
        journal.save()
        execute(
            SimpleNamespace(
                execute=True,
                sender_domain_verified=True,
                sender="billing@intervucopilot.in",
                recipient="acceptance-recipient@example.invalid",
                evidence=str(directory),
                pg_bin=pg_bin,
            ),
            journal=journal,
        )
        journal.state["stage"] = "finished"
    finally:
        publication.key = ""
        values.clear()
        credential = ""
        storage.close()
        transport.close()
        for name in ("RESEND_API_KEY", "EMAIL_ASSET_BASE_URL", "EMAIL_WEBSITE_ORIGIN"):
            os.environ.pop(name, None)
        journal.state["status"] = "stopped"
        journal.state["publication_credentials_cleared"] = True
        journal.save()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pg-bin", required=True)
    parser.add_argument("--reconcile-publication", action="store_true")
    parser.add_argument("--continue-verified-email", action="store_true")
    args = parser.parse_args()
    try:
        if args.reconcile_publication:
            reconcile_publication()
        elif args.continue_verified_email:
            continue_verified_email(args.pg_bin)
        else:
            run(args.pg_bin)
    except (ValueError, AssertionError, OSError, requests.RequestException) as error:
        print(
            "Publication/check stopped:",
            type(error).__name__,
            "— see redacted stage and HTTP journal; do not retry",
        )
        raise SystemExit(1) from None
    if args.reconcile_publication:
        print("Three public assets verified; zero emails sent by this recovery step.")
    else:
        print("Two emails accepted; inbox/delivery evidence is separate.")
