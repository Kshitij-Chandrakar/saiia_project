from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import email_unsubscribe
from app.email.unsubscribe import MarketingUnsubscribeService


class FakeUnsubscribeClient:
    def __init__(self) -> None:
        self.consumed_hashes: list[str] = []

    def insert_token(self, **kwargs: object) -> None:
        raise AssertionError("public unsubscribe must not create tokens")

    def consume_token(self, *, token_hash: str) -> bool:
        self.consumed_hashes.append(token_hash)
        return True

    def get_marketing_opt_in(self, *, user_id: str) -> bool:
        return True


def _client(service: MarketingUnsubscribeService) -> TestClient:
    app = FastAPI()
    app.include_router(email_unsubscribe.router, prefix="/api/email")
    app.dependency_overrides[email_unsubscribe.get_marketing_unsubscribe_service] = lambda: service
    return TestClient(app)


def test_public_unsubscribe_consumes_token_without_login_or_account_disclosure() -> None:
    fake = FakeUnsubscribeClient()
    client = _client(MarketingUnsubscribeService(client=fake))

    response = client.post(
        "/api/email/unsubscribe",
        json={"token": "A" * 32},
    )

    assert response.status_code == 200
    assert response.json() == {
        "success": True,
        "message": "Your promotional email preference has been updated if the link was valid.",
    }
    assert len(fake.consumed_hashes) == 1
    assert "user_id" not in response.text
    assert "user@example.com" not in response.text
    assert "token_hash" not in response.text


def test_invalid_public_unsubscribe_token_returns_same_generic_response() -> None:
    fake = FakeUnsubscribeClient()
    client = _client(MarketingUnsubscribeService(client=fake))

    response = client.post("/api/email/unsubscribe", json={"token": "invalid"})

    assert response.status_code == 200
    assert response.json()["message"] == (
        "Your promotional email preference has been updated if the link was valid."
    )
    assert fake.consumed_hashes == []


def test_public_unsubscribe_storage_failure_is_generic() -> None:
    class FailingClient(FakeUnsubscribeClient):
        def consume_token(self, *, token_hash: str) -> bool:
            from app.email.unsubscribe import MarketingUnsubscribeStorageError

            raise MarketingUnsubscribeStorageError("internal storage details")

    client = _client(MarketingUnsubscribeService(client=FailingClient()))

    response = client.post("/api/email/unsubscribe", json={"token": "A" * 32})

    assert response.status_code == 503
    assert response.json() == {
        "detail": "Unable to update your promotional email preference right now."
    }
    assert "internal storage details" not in response.text
