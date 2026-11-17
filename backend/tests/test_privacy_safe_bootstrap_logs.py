"""No raw PostgREST response/transport payload in privacy-related bootstrap logs."""

from types import SimpleNamespace

import pytest
import requests
from app.cloud.profile_bootstrap import (
    SupabaseProfileBootstrapError,
    SupabaseRestClient,
)


def test_bootstrap_diagnostics_exclude_response_and_transport_contents(caplog):
    client = object.__new__(SupabaseRestClient)
    secret = "SYNTHETIC_PRIVATE_PAYLOAD_AND_TOKEN"
    with pytest.raises(SupabaseProfileBootstrapError):
        client._raise_for_response(
            "profiles", "select", SimpleNamespace(status_code=403, text=secret)
        )
    with pytest.raises(SupabaseProfileBootstrapError) as error:
        client._raise_for_request_error(
            "profiles", "select", requests.RequestException(secret)
        )
    assert secret not in caplog.text
    assert error.value.__cause__ is None
    assert "status=403" in caplog.text and "status=request_error" in caplog.text
