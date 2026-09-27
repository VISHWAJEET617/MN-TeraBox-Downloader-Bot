import asyncio
import http.server
import os
import threading
from types import SimpleNamespace
from unittest import mock

import pytest

from plugins import tera


# ---------- pure helpers ----------

@pytest.mark.parametrize("url", [
    "https://terabox.com/s/1abcDEF",
    "https://www.1024terabox.com/s/1abc",
    "https://teraboxapp.com/s/1xyz",
    "https://terabox-api.mn-bots.workers.dev/dl/abc/video.mp4",
])
def test_terabox_regex_matches(url):
    assert tera.re.match(tera.TERABOX_REGEX, url)


@pytest.mark.parametrize("url", [
    "https://example.com/s/abc",
    "https://terabox.com/share/abc",
])
def test_terabox_regex_rejects(url):
    assert not tera.re.match(tera.TERABOX_REGEX, url)


def test_extract_url_from_surrounding_text():
    text = "please get this https://terabox.com/s/1abc thanks"
    assert tera.extract_url(text) == "https://terabox.com/s/1abc"
    assert tera.extract_url(None) == ""


def test_get_size():
    assert tera.get_size(500) == "500 bytes"
    assert tera.get_size(2048) == "2.00 KB"
    assert tera.get_size(5 * 1024 ** 2) == "5.00 MB"
    assert tera.get_size(3 * 1024 ** 3) == "3.00 GB"


def test_clean_filename():
    assert tera.clean_filename('../a:b*c?.mp4') == "a_b_c_.mp4"
    assert tera.clean_filename("") == "download"
    assert tera.clean_filename(None) == "download"


def test_filename_from_response():
    resp = SimpleNamespace(headers={"content-disposition": "attachment; filename*=UTF-8''my%20video.mp4"})
    assert tera.filename_from_response(resp, "x") == "my video.mp4"
    resp = SimpleNamespace(headers={"content-disposition": 'attachment; filename="clip.mkv"'})
    assert tera.filename_from_response(resp, "x") == "clip.mkv"
    resp = SimpleNamespace(headers={})
    assert tera.filename_from_response(resp, "fallback.bin") == "fallback.bin"


def test_api_download_options_and_url():
    data = {"qualities": {"360p": "u360", "720p": "u720", "1080p": ""}, "best_quality": "720p"}
    assert tera.get_api_download_options(data) == {"360p": "u360", "720p": "u720"}
    assert tera.get_api_download_url(data) == "u720"

    assert tera.get_api_download_options({"media_url": "m"}) == {"Stream": "m"}
    assert tera.get_api_download_options({"direct_download_url": "d"}) == {"Direct": "d"}
    assert tera.get_api_download_url({"direct_download_url": "d"}) == "d"


def _json_response(payload):
    resp = mock.Mock()
    resp.json.return_value = payload
    resp.raise_for_status.return_value = None
    return resp


def test_get_api_file_info():
    payload = {
        "success": True, "filename": "a/b.mp4", "size": 2048,
        "qualities": {"720p": "u720"}, "best_quality": "720p",
    }
    with mock.patch.object(tera.requests, "get", return_value=_json_response(payload)) as get:
        info = tera.get_api_file_info("https://terabox.com/s/1abc")
    assert "url=https%3A%2F%2Fterabox.com%2Fs%2F1abc" in get.call_args[0][0]
    assert info["name"] == "b.mp4"
    assert info["download_link"] == "u720"
    assert info["size_str"] == "2.00 KB"
    assert info["source"] == "api"


def test_get_api_file_info_failure():
    with mock.patch.object(tera.requests, "get", return_value=_json_response({"success": False, "message": "nope"})):
        with pytest.raises(ValueError, match="nope"):
            tera.get_api_file_info("https://terabox.com/s/1abc")


def test_get_download_info_stream_link_skips_api():
    url = "https://terabox-api.mn-bots.workers.dev/dl/abc/video.mp4"
    with mock.patch.object(tera, "get_api_file_info") as api:
        info = tera.get_download_info(url)
    api.assert_not_called()
    assert info["name"] == "video.mp4" and info["source"] == "stream"


def test_get_download_info_falls_back_to_scraper(monkeypatch):
    monkeypatch.setattr(tera.TERABOX, "USE_API_DOWNLOAD", True)
    monkeypatch.setattr(tera.TERABOX, "API_FALLBACK_TO_SCRAPER", True)
    with mock.patch.object(tera, "get_api_file_info", side_effect=ValueError("down")), \
            mock.patch.object(tera, "get_file_info", return_value={"source": "scraper"}) as scraper:
        assert tera.get_download_info("https://terabox.com/s/1abc")["source"] == "scraper"
    scraper.assert_called_once()


def test_get_download_info_no_fallback(monkeypatch):
    monkeypatch.setattr(tera.TERABOX, "USE_API_DOWNLOAD", True)
    monkeypatch.setattr(tera.TERABOX, "API_FALLBACK_TO_SCRAPER", False)
    with mock.patch.object(tera, "get_api_file_info", side_effect=ValueError("down")):
        with pytest.raises(ValueError):
            tera.get_download_info("https://terabox.com/s/1abc")


def test_cache_keys_dedupe():
    info = {"original_url": "a", "resolved_url": "a", "download_link": "b"}
    assert tera.get_cache_keys(info) == ["a", "b"]


# ---------- quality selection ----------

def test_quality_selection_lifecycle():
    async def run():
        info = {"download_options": {"360p": "a", "720p": "b"}, "best_quality": "720p"}
        sid = tera.cache_quality_selection(1, info)
        assert tera.get_cached_quality_selection(sid, 2) is None  # other user
        assert tera.get_cached_quality_selection(sid, 1)["info"] is info

        markup = tera.build_quality_buttons(sid, info)
        labels = [row[0].text for row in markup.inline_keyboard]
        assert labels == ["360p", "720p ⭐"]

        tera.QUALITY_SELECTIONS[sid]["expires_at"] = 0
        tera.purge_expired_selections()
        assert sid not in tera.QUALITY_SELECTIONS
    asyncio.run(run())


# ---------- download ----------

class _Handler(http.server.BaseHTTPRequestHandler):
    body = os.urandom(3 * 1024 * 1024 + 17)

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Length", str(len(self.body)))
        self.send_header("Content-Disposition", 'attachment; filename="served.bin"')
        self.end_headers()
        self.wfile.write(self.body)

    def log_message(self, *args):
        pass


@pytest.fixture
def http_url():
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}/file"
    server.shutdown()


def test_download_file(tmp_path, http_url, monkeypatch):
    monkeypatch.setenv("NO_PROXY", "127.0.0.1")
    name, path = tera.download_file(http_url, "fallback", str(tmp_path))
    assert name == "served.bin"
    with open(path, "rb") as f:
        assert f.read() == _Handler.body


# ---------- handler flow (fake pyrogram objects) ----------

class FakeMessage:
    def __init__(self, text="", chat_id=42, user_id=7):
        self.text = text
        self.chat = SimpleNamespace(id=chat_id)
        self.from_user = SimpleNamespace(id=user_id)
        self.replies = []
        self.deleted = False

    async def reply(self, text, **kwargs):
        self.replies.append((text, kwargs))
        return FakeMessage(text)

    reply_text = reply

    async def delete(self):
        self.deleted = True


class FakeClient:
    def __init__(self):
        self.sent = []

    async def send_document(self, chat_id, document, **kwargs):
        self.sent.append((chat_id, document, kwargs))
        msg = FakeMessage()
        msg.document = SimpleNamespace(file_id="FILE123")
        return msg


def test_handle_terabox_downloads_and_returns_promptly(monkeypatch, tmp_path, http_url):
    monkeypatch.setenv("NO_PROXY", "127.0.0.1")
    monkeypatch.setattr(tera, "IS_VERIFY", False)
    monkeypatch.setattr(tera.CHANNEL, "ID", -1001)
    monkeypatch.setattr(tera, "get_cached_upload", lambda info: None)
    saved = {}
    monkeypatch.setattr(tera, "save_cached_upload", lambda info, fid: saved.update(fid=fid))
    monkeypatch.setattr(tera, "get_download_info", lambda url: {
        "name": "x.bin", "download_link": http_url, "size_bytes": 0, "size_str": "0 bytes",
        "resolved_url": url, "original_url": url, "download_options": {"Direct": http_url},
    })

    client = FakeClient()
    msg = FakeMessage("get https://terabox.com/s/1abc")

    async def run():
        # Must finish quickly: the 12h auto-delete is scheduled, not awaited
        await asyncio.wait_for(tera.handle_terabox(client, msg), timeout=15)
        assert len(tera.PENDING_DELETES) == 1
        for t in list(tera.PENDING_DELETES):
            t.cancel()

    asyncio.run(run())

    assert [c[0] for c in client.sent] == [-1001, 42]
    assert client.sent[1][2]["protect_content"] is True
    assert client.sent[1][2]["file_name"] == "served.bin"
    assert saved["fid"] == "FILE123"
    assert any("deleted from your chat" in r[0] for r in msg.replies)


def test_handle_terabox_multiple_qualities_prompts(monkeypatch):
    monkeypatch.setattr(tera, "IS_VERIFY", False)
    monkeypatch.setattr(tera, "get_cached_upload", lambda info: None)
    monkeypatch.setattr(tera, "get_download_info", lambda url: {
        "name": "v.mp4", "download_link": "b", "size_str": "0 bytes",
        "download_options": {"360p": "a", "720p": "b"}, "best_quality": "720p",
    })
    msg = FakeMessage("https://terabox.com/s/1abc")
    asyncio.run(tera.handle_terabox(FakeClient(), msg))
    text, kwargs = msg.replies[-1]
    assert "Select download quality" in text
    assert kwargs["reply_markup"].inline_keyboard


def test_handle_terabox_info_error(monkeypatch):
    monkeypatch.setattr(tera, "IS_VERIFY", False)
    monkeypatch.setattr(tera, "get_cached_upload", lambda info: None)

    def boom(url):
        raise ValueError("bad link")
    monkeypatch.setattr(tera, "get_download_info", boom)
    msg = FakeMessage("https://terabox.com/s/1abc")
    asyncio.run(tera.handle_terabox(FakeClient(), msg))
    assert "bad link" in msg.replies[-1][0]


def test_schedule_delete():
    async def run():
        msg = FakeMessage()
        await tera.schedule_delete(msg, 0)
        assert msg.deleted
    asyncio.run(run())
