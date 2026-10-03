from decimal import Decimal
from urllib.parse import parse_qs, urlparse

import pytest
import requests
import responses

from apps.diagnosis.providers.base import (
    ImageInput,
    ProviderAuthError,
    ProviderQuotaError,
    ProviderRequestError,
    ProviderResponseError,
    ProviderTemporaryError,
)
from apps.diagnosis.providers.kindwise import KindwiseProvider

from .conftest import KINDWISE_URL

IMAGES = [ImageInput(filename="leaf.jpg", content=b"\xff\xd8fake")]


@pytest.fixture
def provider():
    return KindwiseProvider(
        api_key="secret-key", base_url="https://kindwise.test/api/v1/", timeout=(1, 1), language="en"
    )


@responses.activate
def test_identify_parses_result_and_sends_expected_request(provider, kindwise_response):
    responses.post(KINDWISE_URL, json=kindwise_response, status=201)

    result = provider.identify(IMAGES, latitude=-0.33, longitude=37.65)

    request = responses.calls[0].request
    assert request.headers["Api-Key"] == "secret-key"
    assert request.headers["Content-Type"].startswith("multipart/form-data")
    query = parse_qs(urlparse(request.url).query)
    assert query["language"] == ["en"]
    assert "treatment" in query["details"][0].split(",")
    assert b'name="latitude"' in request.body and b"-0.33" in request.body

    assert result.external_ref == "SChIQy84K8bvPtd"
    assert result.model_version == "crop_health:1.1.1"
    assert result.is_plant_probability == Decimal("1.0000")
    # Suggestions are sorted by probability, highest first.
    assert [s.name for s in result.disease_suggestions][:2] == ["late blight", "healthy"]
    top = result.disease_suggestions[0]
    assert top.probability == Decimal("0.9806")
    assert top.is_healthy is False
    assert "language" not in top.details and "entity_id" not in top.details
    assert next(s for s in result.disease_suggestions if s.name == "healthy").is_healthy is True
    assert result.crop_suggestions[0].name == "tomato"


@pytest.mark.parametrize(
    ("status", "error"),
    [
        (401, ProviderAuthError),
        (429, ProviderQuotaError),
        (400, ProviderRequestError),
        (500, ProviderTemporaryError),
        (503, ProviderTemporaryError),
    ],
)
@responses.activate
def test_http_errors_map_to_provider_errors(provider, status, error):
    responses.post(KINDWISE_URL, body="error", status=status)
    with pytest.raises(error) as exc_info:
        provider.identify(IMAGES)
    assert exc_info.value.status_code == status


@responses.activate
def test_timeout_is_temporary(provider):
    responses.post(KINDWISE_URL, body=requests.ReadTimeout("slow"))
    with pytest.raises(ProviderTemporaryError):
        provider.identify(IMAGES)


@responses.activate
def test_async_style_body_without_result_is_bad_response(provider):
    responses.post(KINDWISE_URL, json={"access_token": "x", "status": "CREATED"}, status=201)
    with pytest.raises(ProviderResponseError):
        provider.identify(IMAGES)


@responses.activate
def test_non_json_body_is_bad_response(provider):
    responses.post(KINDWISE_URL, body="<html>", status=201)
    with pytest.raises(ProviderResponseError):
        provider.identify(IMAGES)


def test_missing_api_key_is_auth_error():
    with pytest.raises(ProviderAuthError):
        KindwiseProvider(api_key="", base_url="https://kindwise.test", timeout=(1, 1))


def test_no_images_rejected(provider):
    with pytest.raises(ProviderRequestError):
        provider.identify([])
