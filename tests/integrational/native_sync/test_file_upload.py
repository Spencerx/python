from urllib.parse import parse_qs, urlparse
import pytest
import urllib

from Cryptodome.Cipher import AES
from unittest.mock import patch
from pubnub.exceptions import PubNubException
from pubnub.pubnub import PubNub
from tests.integrational.vcr_helper import pn_vcr  # , pn_vcr_with_empty_body_request
from tests.helper import pnconf_env_copy, pnconf_enc_env_copy, pnconf_env_copy
from pubnub.endpoints.file_operations.publish_file_message import PublishFileMessage
from pubnub.models.consumer.file import (
    PNSendFileResult, PNGetFilesResult, PNDownloadFileResult,
    PNGetFileDownloadURLResult, PNDeleteFileResult, PNFetchFileUploadS3DataResult,
    PNPublishFileMessageResult
)

CHANNEL = "files_native_sync_ch"

pubnub = PubNub(pnconf_env_copy(disable_config_locking=True))
pubnub.config.uuid = "files_native_sync_uuid"


def send_file(file_for_upload, cipher_key=None, pass_binary=False, timetoken_override=None, pubnub_instance=None):
    if not pubnub_instance:
        pubnub_instance = pubnub
    if cipher_key:
        pubnub_instance.config.cipher_key = cipher_key

    with open(file_for_upload.strpath, "rb") as fd:
        if pass_binary:
            fd = fd.read()

        send_file_endpoint = pubnub_instance.send_file() \
            .channel(CHANNEL) \
            .file_name(file_for_upload.basename) \
            .message({"test_message": "test"}) \
            .should_store(True) \
            .ttl(222) \
            .file_object(fd)

        if timetoken_override:
            send_file_endpoint = send_file_endpoint.ptto(timetoken_override)

        envelope = send_file_endpoint.sync()

    assert isinstance(envelope.result, PNSendFileResult)
    assert envelope.result.name
    assert envelope.result.timestamp
    assert envelope.result.file_id
    return envelope


@pn_vcr.use_cassette(
    "tests/integrational/fixtures/native_sync/file_upload/list_files.json", serializer="pn_json",
    filter_query_parameters=('pnsdk',)
)
def test_list_files(file_upload_test_data, file_for_upload):
    envelope = pubnub.list_files().channel(CHANNEL).sync()
    files = envelope.result.data
    for i in range(len(files) - 1):
        file = files[i]
        pubnub.delete_file().channel(CHANNEL).file_id(file["id"]).file_name(file["name"]).sync()

    envelope = send_file(file_for_upload, pass_binary=True)

    envelope = pubnub.list_files().channel(CHANNEL).sync()

    assert isinstance(envelope.result, PNGetFilesResult)
    assert envelope.result.count == 1
    assert file_upload_test_data["UPLOADED_FILENAME"] == envelope.result.data[0]["name"]


@pn_vcr.use_cassette(
    "tests/integrational/fixtures/native_sync/file_upload/list_files_with_limit.json", serializer="pn_json",
    filter_query_parameters=('pnsdk',)
)
def test_list_files_with_limit(file_for_upload, file_upload_test_data):
    envelope = send_file(file_for_upload, pass_binary=True)
    envelope = send_file(file_for_upload, pass_binary=True)
    envelope = pubnub.list_files().channel(CHANNEL).limit(2).sync()
    assert isinstance(envelope.result, PNGetFilesResult)
    assert envelope.result.count == 2
    assert file_upload_test_data["UPLOADED_FILENAME"] == envelope.result.data[0]["name"]


@pn_vcr.use_cassette(
    "tests/integrational/fixtures/native_sync/file_upload/list_files_with_page.json", serializer="pn_json",
    filter_query_parameters=('pnsdk',)
)
def test_list_files_with_page(file_for_upload, file_upload_test_data):
    envelope = send_file(file_for_upload, pass_binary=True)
    envelope = send_file(file_for_upload, pass_binary=True)
    envelope = pubnub.list_files().channel(CHANNEL).limit(2).sync()
    assert isinstance(envelope.result, PNGetFilesResult)
    assert envelope.result.count == 2
    assert envelope.result.next is not None
    next_page = envelope.result.next
    file_ids = [envelope.result.data[0]['id'], envelope.result.data[1]['id']]
    envelope = pubnub.list_files().channel(CHANNEL).limit(2).next(next_page).sync()
    assert isinstance(envelope.result, PNGetFilesResult)
    assert envelope.result.count == 2
    assert envelope.result.next is not None
    assert envelope.result.data[0]['id'] not in file_ids
    assert envelope.result.data[1]['id'] not in file_ids
    assert file_upload_test_data["UPLOADED_FILENAME"] == envelope.result.data[0]["name"]


@pn_vcr.use_cassette(
    "tests/integrational/fixtures/native_sync/file_upload/send_and_download_file_using_bytes_object.json",
    filter_query_parameters=('pnsdk',), serializer="pn_json"
)
def test_send_and_download_file_using_bytes_object(file_for_upload, file_upload_test_data):
    envelope = send_file(file_for_upload, pass_binary=True)

    download_envelope = pubnub.download_file() \
        .channel(CHANNEL) \
        .file_id(envelope.result.file_id) \
        .file_name(envelope.result.name).sync()

    assert isinstance(download_envelope.result, PNDownloadFileResult)
    data = download_envelope.result.data
    assert data == bytes(file_upload_test_data["FILE_CONTENT"], "utf-8")


# TODO: fix VCR to handle utf-8 properly
# @pn_vcr.use_cassette(
#     "tests/integrational/fixtures/native_sync/file_upload/send_and_download_encrypted_file.json",
#     filter_query_parameters=('pnsdk',), serializer="pn_json"
# )
def test_send_and_download_encrypted_file(file_for_upload, file_upload_test_data):
    cipher_key = "silly_walk"
    with patch("pubnub.crypto.PubNubCryptodome.get_initialization_vector", return_value="knightsofni12345"):
        envelope = send_file(file_for_upload, cipher_key=cipher_key)

        download_envelope = pubnub.download_file() \
            .channel(CHANNEL) \
            .file_id(envelope.result.file_id) \
            .file_name(envelope.result.name).sync()

        assert isinstance(download_envelope.result, PNDownloadFileResult)
        data = download_envelope.result.data
        assert data == bytes(file_upload_test_data["FILE_CONTENT"], "utf-8")


# TODO: fix VCR to handle utf-8 properly
# @pn_vcr_with_empty_body_request.use_cassette(
#     "tests/integrational/fixtures/native_sync/file_upload/file_size_exceeded_maximum_size.json", serializer="pn_json",
#     filter_query_parameters=('pnsdk',)
# )
def test_file_exceeded_maximum_size(file_for_upload_10mb_size):
    with pytest.raises(PubNubException) as exception:
        send_file(file_for_upload_10mb_size)

    assert "Your proposed upload exceeds the maximum allowed size" in str(exception.value)


# @pn_vcr.use_cassette(
#     "tests/integrational/fixtures/native_sync/file_upload/delete_file.json", serializer="pn_json",
#     filter_query_parameters=('pnsdk',)
# )
def test_delete_file(file_for_upload):
    envelope = send_file(file_for_upload)

    delete_envelope = pubnub.delete_file() \
        .channel(CHANNEL) \
        .file_id(envelope.result.file_id) \
        .file_name(envelope.result.name).sync()

    assert isinstance(delete_envelope.result, PNDeleteFileResult)


# @pn_vcr.use_cassette(
#     "tests/integrational/fixtures/native_sync/file_upload/download_url.json", serializer="pn_json",
#     filter_query_parameters=('pnsdk',)
# )
def test_get_file_url(file_for_upload):
    envelope = send_file(file_for_upload)

    file_url_envelope = pubnub.get_file_url() \
        .channel(CHANNEL) \
        .file_id(envelope.result.file_id) \
        .file_name(envelope.result.name).sync()

    assert isinstance(file_url_envelope.result, PNGetFileDownloadURLResult)
    assert file_url_envelope.result.file_url is not None


# @pn_vcr.use_cassette(
#     "tests/integrational/fixtures/native_sync/file_upload/download_url_check_auth_key_in_url.json",
#     filter_query_parameters=('pnsdk',), serializer="pn_json",
# )
def test_get_file_url_has_auth_key_in_url_and_signature(file_upload_test_data):
    pubnub = PubNub(pnconf_env_copy())
    pubnub.config.uuid = "files_native_sync_uuid"
    pubnub.config.auth_key = "test_auth_key"

    file_url_envelope = pubnub.get_file_url() \
        .channel(CHANNEL) \
        .file_id("random_file_id") \
        .file_name("random_file_name").sync()

    assert "auth=test_auth_key" in str(file_url_envelope.status.client_request.url)


# @pn_vcr.use_cassette(
#     "tests/integrational/fixtures/native_sync/file_upload/fetch_file_upload_data.json", serializer="pn_json",
#     filter_query_parameters=('pnsdk',)
# )
def test_fetch_file_upload_s3_data(file_upload_test_data):
    envelope = pubnub._fetch_file_upload_s3_data() \
        .channel(CHANNEL) \
        .file_name(file_upload_test_data["UPLOADED_FILENAME"]).sync()

    assert isinstance(envelope.result, PNFetchFileUploadS3DataResult)


# @pn_vcr.use_cassette(
#     "tests/integrational/fixtures/native_sync/file_upload/publish_file_message.json", serializer="pn_json",
#     filter_query_parameters=('pnsdk',)
# )
def test_publish_file_message():
    envelope = PublishFileMessage(pubnub) \
        .channel(CHANNEL) \
        .meta({}) \
        .message({"test": "test"}) \
        .file_id("2222") \
        .file_name("test") \
        .should_store(True) \
        .ttl(222).sync()

    assert isinstance(envelope.result, PNPublishFileMessageResult)


# @pn_vcr.use_cassette(
#     "tests/integrational/fixtures/native_sync/file_upload/publish_file_message_encrypted.json", serializer="pn_json",
#     filter_query_parameters=('pnsdk',)
# )
def test_publish_file_message_with_encryption():
    envelope = PublishFileMessage(pubnub) \
        .channel(CHANNEL) \
        .meta({}) \
        .message({"test": "test"}) \
        .file_id("2222") \
        .file_name("test") \
        .should_store(True) \
        .ttl(222).sync()

    assert isinstance(envelope.result, PNPublishFileMessageResult)


# @pn_vcr.use_cassette(
#     "tests/integrational/fixtures/native_sync/file_upload/publish_file_message_with_ptto.json", serializer="pn_json",
#     filter_query_parameters=('pnsdk',)
# )
def test_publish_file_message_with_overriding_time_token():
    timetoken_to_override = 16057799474000000
    envelope = PublishFileMessage(pubnub) \
        .channel(CHANNEL) \
        .meta({}) \
        .message({"test": "test"}) \
        .file_id("2222") \
        .file_name("test") \
        .should_store(True) \
        .replicate(True) \
        .ptto(timetoken_to_override) \
        .ttl(222).sync()

    assert isinstance(envelope.result, PNPublishFileMessageResult)
    # note: for requests url is string, for httpx is object
    if hasattr(envelope.status.client_request.url, 'query'):
        query = urllib.parse.parse_qs(envelope.status.client_request.url.query.decode())
    else:
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(envelope.status.client_request.url).query)
    assert "ptto" in query


# @pn_vcr.use_cassette(
#     "tests/integrational/fixtures/native_sync/file_upload/send_file_with_ptto.json", serializer="pn_json",
#     filter_query_parameters=('pnsdk',)
# )
def test_send_file_with_timetoken_override(file_for_upload):
    send_file(file_for_upload, pass_binary=True, timetoken_override=16057799474000000)


# @pn_vcr.use_cassette(
#     "tests/integrational/fixtures/native_sync/file_upload/send_and_download_gcm_encrypted_file.json",
#     filter_query_parameters=('pnsdk',), serializer='pn_json'
# )
def test_send_and_download_gcm_encrypted_file(file_for_upload, file_upload_test_data):
    cipher_key = "silly_walk"

    config = pnconf_enc_env_copy()
    config.cipher_mode = AES.MODE_GCM
    config.fallback_cipher_mode = AES.MODE_CBC
    config.cipher_key = cipher_key
    pubnub = PubNub(config)

    with patch("pubnub.crypto.PubNubCryptodome.get_initialization_vector", return_value="knightsofni12345"):
        envelope = send_file(file_for_upload, cipher_key=cipher_key, pubnub_instance=pubnub)

        download_envelope = pubnub.download_file() \
            .channel(CHANNEL) \
            .file_id(envelope.result.file_id) \
            .file_name(envelope.result.name).sync()

        assert isinstance(download_envelope.result, PNDownloadFileResult)
        data = download_envelope.result.data
        assert data == bytes(file_upload_test_data["FILE_CONTENT"], "utf-8")


# @pn_vcr.use_cassette(
#     "tests/integrational/fixtures/native_sync/file_upload/send_and_download_encrypted_file_fallback_decode.json",
#     filter_query_parameters=('pnsdk',), serializer='pn_json'
# )
def test_send_and_download_encrypted_file_fallback_decode(file_for_upload, file_upload_test_data):
    config_cbc = pnconf_enc_env_copy()
    pn_cbc = PubNub(config_cbc)
    config_gcm = pnconf_enc_env_copy()
    config_gcm.cipher_mode = AES.MODE_GCM
    config_gcm.fallback_cipher_mode = AES.MODE_CBC
    pn_gcm = PubNub(config_gcm)

    cipher_key = "silly_walk"
    with patch("pubnub.crypto.PubNubCryptodome.get_initialization_vector", return_value="knightsofni12345"):
        envelope = send_file(file_for_upload, cipher_key=cipher_key, pubnub_instance=pn_cbc)

        download_envelope = pn_gcm.download_file() \
            .channel(CHANNEL) \
            .file_id(envelope.result.file_id) \
            .file_name(envelope.result.name) \
            .cipher_key(cipher_key).sync()

        assert isinstance(download_envelope.result, PNDownloadFileResult)
        data = download_envelope.result.data
        assert data == bytes(file_upload_test_data["FILE_CONTENT"], "utf-8")


@pn_vcr.use_cassette(
    "tests/integrational/fixtures/native_sync/file_upload/publish_file_message_with_custom_type.json",
    filter_query_parameters=('pnsdk',), serializer='pn_json'
)
def test_publish_file_message_with_custom_type():
    with pn_vcr.use_cassette(
        "tests/integrational/fixtures/native_sync/file_upload/publish_file_message_with_custom_type.json",
         filter_query_parameters=('pnsdk',), serializer='pn_json') as cassette:

        pubnub = PubNub(pnconf_env_copy())
        envelope = pubnub.publish_file_message() \
            .channel(CHANNEL) \
            .message({"test": "test"}) \
            .meta({}) \
            .message({"test": "test"}) \
            .file_id("2222") \
            .file_name("test") \
            .custom_message_type("test_message").sync()

        assert isinstance(envelope.result, PNPublishFileMessageResult)
        assert len(cassette) == 1
        uri = urlparse(cassette.requests[0].uri)
        query = parse_qs(uri.query)
        assert 'custom_message_type' in query.keys()
        assert query['custom_message_type'] == ['test_message']


def test_delete_all_files():
    envelope = pubnub.list_files().channel(CHANNEL).sync()
    files = envelope.result.data
    for i in range(len(files)):
        file = files[i]
        pubnub.delete_file().channel(CHANNEL).file_id(file["id"]).file_name(file["name"]).sync()
    envelope = pubnub.list_files().channel(CHANNEL).sync()

    assert isinstance(envelope.result, PNGetFilesResult)
    assert envelope.result.count == 0
