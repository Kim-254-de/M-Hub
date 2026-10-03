import base64
import json

import pytest
import requests
import responses
from django.core.cache import cache

from apps.products.pcpb import extract_keys, parse_reg_no
from apps.purchases.integrations import mpesa, ocr

from .conftest import OAUTH_URL, OCR_URL, QUERY_URL, STK_URL, image_bytes, mock_stk_push, ocr_response


@pytest.fixture(autouse=True)
def clear_cache():
    cache.clear()


# --- PCPB number parsing -------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "PCPB (CR) 0856",
        "PCPB(CR)0856",
        "pcpb (cr) 856",
        "Reg. No: PCPB(CR)0856\nKeep out of reach of children",
        "PCP8 (CR) O856",  # OCR: B->8, 0->O
        "PCPB [CR] 0856",
        "PCPB CR 0856",
    ],
)
def test_pcpb_variants_normalise_to_same_key(text):
    assert parse_reg_no(text) == "CR:856"


def test_pcpb_rejects_non_numbers():
    assert parse_reg_no("PCPB approved") is None
    assert parse_reg_no("Batch 0856") is None


def test_extract_keys_finds_all_unique_numbers():
    text = "PCPB(CR)0856 ... PCPB (CR) 1201 ... PCPB(CR)0856"
    assert extract_keys(text) == ["CR:856", "CR:1201"]


# --- M-Pesa client ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("0712345678", "254712345678"),
        ("+254712345678", "254712345678"),
        ("254712345678", "254712345678"),
        ("712345678", "254712345678"),
        ("0112 345 678", "254112345678"),
    ],
)
def test_normalize_phone(raw, expected):
    assert mpesa.normalize_phone(raw) == expected


@pytest.mark.parametrize("raw", ["", "12345", "0812345678", "2547123456789"])
def test_normalize_phone_rejects_invalid(raw):
    with pytest.raises(ValueError):
        mpesa.normalize_phone(raw)


@responses.activate
def test_stk_push_sends_daraja_body_and_caches_token(settings):
    mock_stk_push()
    client = mpesa.MpesaClient.from_settings()

    client.stk_push(
        phone="254712345678",
        amount=1300,
        account_reference="AGR-7F3KXYZW-LONG",
        description="AgriSense purchase",
        callback_url="https://x/cb",
    )
    client.stk_push(
        phone="254712345678", amount=1, account_reference="R", description="D", callback_url="https://x"
    )

    assert len([c for c in responses.calls if c.request.url.startswith(OAUTH_URL)]) == 1
    body = json.loads(responses.calls[1].request.body)
    assert responses.calls[1].request.headers["Authorization"] == "Bearer token-abc"
    assert body["Amount"] == 1300 and isinstance(body["Amount"], int)
    assert body["PartyA"] == body["PhoneNumber"] == "254712345678"
    assert body["BusinessShortCode"] == body["PartyB"] == "174379"
    assert len(body["Timestamp"]) == 14
    assert base64.b64decode(body["Password"]).decode() == f"174379test-passkey{body['Timestamp']}"
    assert body["AccountReference"] == "AGR-7F3KXYZW"  # max 12
    assert len(body["TransactionDesc"]) <= 13


@responses.activate
def test_invalid_token_is_refreshed_once():
    responses.get(OAUTH_URL, json={"access_token": "t1", "expires_in": "3599"})
    responses.post(
        STK_URL, status=404, json={"errorCode": "404.001.03", "errorMessage": "Invalid Access Token"}
    )
    mock_stk_push()
    client = mpesa.MpesaClient.from_settings()

    result = client.stk_push(
        phone="254712345678", amount=5, account_reference="R", description="D", callback_url="u"
    )

    assert result.checkout_request_id.startswith("ws_CO_")


@pytest.mark.parametrize(
    ("status", "body", "error"),
    [
        (500, {"errorCode": "500.003.02", "errorMessage": "System is busy"}, mpesa.MpesaTemporaryError),
        (
            400,
            {"errorCode": "400.002.02", "errorMessage": "Bad Request - Invalid PhoneNumber"},
            mpesa.MpesaRequestError,
        ),
        (500, {"errorCode": "500.001.1001", "errorMessage": "Wrong credentials"}, mpesa.MpesaRequestError),
    ],
)
@responses.activate
def test_stk_push_error_mapping(status, body, error):
    responses.get(OAUTH_URL, json={"access_token": "t", "expires_in": "3599"})
    responses.post(STK_URL, status=status, json=body)
    with pytest.raises(error):
        mpesa.MpesaClient.from_settings().stk_push(
            phone="254712345678", amount=5, account_reference="R", description="D", callback_url="u"
        )


@responses.activate
def test_stk_push_timeout_is_temporary():
    responses.get(OAUTH_URL, json={"access_token": "t", "expires_in": "3599"})
    responses.post(STK_URL, body=requests.ReadTimeout("slow"))
    with pytest.raises(mpesa.MpesaTemporaryError):
        mpesa.MpesaClient.from_settings().stk_push(
            phone="254712345678", amount=5, account_reference="R", description="D", callback_url="u"
        )


@responses.activate
def test_bad_credentials_are_config_errors():
    responses.get(OAUTH_URL, status=400, body="")
    with pytest.raises(mpesa.MpesaConfigError):
        mpesa.MpesaClient.from_settings().stk_push(
            phone="254712345678", amount=5, account_reference="R", description="D", callback_url="u"
        )


def test_missing_credentials_raise_config_error(settings):
    settings.MPESA = {**settings.MPESA, "CONSUMER_KEY": ""}
    with pytest.raises(mpesa.MpesaConfigError):
        mpesa.MpesaClient.from_settings()


@responses.activate
def test_stk_query_pending_and_final():
    responses.get(OAUTH_URL, json={"access_token": "t", "expires_in": "3599"})
    responses.post(
        QUERY_URL,
        status=500,
        json={"errorCode": "500.001.1001", "errorMessage": "The transaction is being processed"},
    )
    responses.post(
        QUERY_URL, json={"ResponseCode": "0", "ResultCode": "1032", "ResultDesc": "Request cancelled by user"}
    )
    client = mpesa.MpesaClient.from_settings()

    assert client.stk_query("ws_CO_1").pending is True
    final = client.stk_query("ws_CO_1")
    assert final.pending is False and final.result_code == "1032"


def test_parse_stk_callback():
    from .conftest import stk_callback

    parsed = mpesa.parse_stk_callback(stk_callback("ws_CO_1"))
    assert parsed["result_code"] == "0"
    assert parsed["mpesa_receipt"] == "SJK7RT61SV"
    assert parsed["amount"] == 1300
    assert parsed["phone"] == "254712345678"

    failed = mpesa.parse_stk_callback(stk_callback("ws_CO_2", result_code=1032))
    assert failed["result_code"] == "1032" and failed["mpesa_receipt"] is None

    with pytest.raises(ValueError):
        mpesa.parse_stk_callback({"foo": "bar"})


# --- OCR client --------------------------------------------------------------------


@responses.activate
def test_ocr_reads_text():
    responses.post(OCR_URL, json=ocr_response("RIDOMIL GOLD\nPCPB(CR)0856"))
    text = ocr.OcrSpaceClient.from_settings().read_text(image_bytes())
    assert "PCPB(CR)0856" in text
    request = responses.calls[0].request
    assert request.headers["apikey"] == "test-ocr-key"
    assert b'name="OCREngine"' in request.body


@responses.activate
def test_ocr_processing_error():
    responses.post(
        OCR_URL, json={"IsErroredOnProcessing": True, "ErrorMessage": ["Unable to recognize the file type"]}
    )
    with pytest.raises(ocr.OcrError):
        ocr.OcrSpaceClient.from_settings().read_text(image_bytes())


@pytest.mark.parametrize(
    ("kwargs", "error"),
    [
        ({"status": 403, "body": "Forbidden"}, ocr.OcrConfigError),
        ({"status": 503, "body": "down"}, ocr.OcrTemporaryError),
        ({"body": requests.ConnectTimeout("x")}, ocr.OcrTemporaryError),
        ({"status": 200, "body": "The API key is invalid"}, ocr.OcrConfigError),
    ],
)
@responses.activate
def test_ocr_error_mapping(kwargs, error):
    responses.post(OCR_URL, **kwargs)
    with pytest.raises(error):
        ocr.OcrSpaceClient.from_settings().read_text(image_bytes())


def test_prepare_image_fits_free_tier_limit():
    import os

    from PIL import Image

    # A noisy 4000x3000 photo is several MB as JPEG.
    big = Image.frombytes("RGB", (4000, 3000), os.urandom(4000 * 3000 * 3))
    buffer = __import__("io").BytesIO()
    big.save(buffer, format="PNG")
    prepared = ocr.prepare_image(buffer.getvalue(), max_bytes=1024 * 1024)
    assert len(prepared) <= 1024 * 1024


def test_prepare_image_rejects_non_images():
    with pytest.raises(ocr.OcrImageError):
        ocr.prepare_image(b"not an image", max_bytes=1024 * 1024)
