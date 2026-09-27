#please give credits https://github.com/MN-BOTS
#  @MrMNTG @MusammilN
import os
import re
import tempfile
import requests
import asyncio
from uuid import uuid4
from datetime import datetime
from urllib.parse import urlencode, urlparse, parse_qs, quote_plus, unquote
from pyrogram import Client 
from pyrogram import filters
from pyrogram.types import Message, CallbackQuery
from verify_patch import IS_VERIFY, is_verified, build_verification_link, HOW_TO_VERIFY
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pymongo import MongoClient
import shutil
from config import CHANNEL, DATABASE, TERABOX
#please give credits https://github.com/MN-BOTS
#  @MrMNTG @MusammilN

mongo_client = MongoClient(DATABASE.URI or None)
db = mongo_client[DATABASE.NAME]

settings_col = db["terabox_settings"]
queue_col = db["terabox_queue"]
last_upload_col = db["terabox_lastupload"]

TERABOX_REGEX = r'https?://(?:www\.)?[^/\s]*tera[^/\s]*\.[a-z]+/(?:s|dl)/[^\s]+'
API_DOWNLOAD_REGEX = r'https?://terabox-api\.mn-bots\.workers\.dev/dl/[^\s]+'
REQUEST_TIMEOUT = 30
QUALITY_SELECTIONS = {}
PENDING_DELETES = set()
QUALITY_SELECTION_TTL = 900
AUTO_DELETE_SECONDS = 43200
DOWNLOAD_CHUNK_SIZE = 1024 * 1024

# add your own cookies like ndus=YzrYlCHteHuixx7IN5r0ABCDFXDGSTGBDJKLBKMKH (or set TERABOX_COOKIE)
COOKIE = TERABOX.COOKIE

HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Encoding": "gzip, deflate, br",
    "Accept-Language": "en-US,en;q=0.9,hi;q=0.8",
    "Connection": "keep-alive",
    "DNT": "1",
    "Host": "www.terabox.app",
    "Upgrade-Insecure-Requests": "1",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/135.0.0.0 Safari/537.36 Edg/135.0.0.0",
    "sec-ch-ua": '"Microsoft Edge";v="135", "Not-A.Brand";v="8", "Chromium";v="135"',
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Cookie": COOKIE,
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
}

DL_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/91.0.4472.124 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;"
              "q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Referer": "https://www.terabox.com/",
    "DNT": "1",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Cookie": COOKIE,
}

def get_size(bytes_len: int) -> str:
    if bytes_len >= 1024 ** 3:
        return f"{bytes_len / 1024**3:.2f} GB"
    if bytes_len >= 1024 ** 2:
        return f"{bytes_len / 1024**2:.2f} MB"
    if bytes_len >= 1024:
        return f"{bytes_len / 1024:.2f} KB"
    return f"{bytes_len} bytes"


def clean_filename(filename: str) -> str:
    filename = os.path.basename(filename or "download")
    return re.sub(r'[\\/:*?"<>|]+', "_", filename).strip() or "download"


def filename_from_response(response, fallback: str) -> str:
    content_disposition = response.headers.get("content-disposition", "")
    filename_match = re.search(r'filename\*?=(?:UTF-8\'\')?["\']?([^"\';]+)', content_disposition, re.IGNORECASE)
    if filename_match:
        return clean_filename(unquote(filename_match.group(1)))
    return clean_filename(fallback)

def get_api_download_url(api_data: dict) -> str:
    qualities = api_data.get("qualities") or {}
    best_quality = api_data.get("best_quality")
    if best_quality and qualities.get(best_quality):
        return qualities[best_quality]
    if qualities:
        return next(iter(qualities.values()))
    return api_data.get("media_url") or api_data.get("direct_download_url", "")


def get_api_download_options(api_data: dict) -> dict:
    options = {}
    qualities = api_data.get("qualities") or {}
    for quality, download_url in qualities.items():
        if download_url:
            options[str(quality)] = download_url

    if options:
        return options

    if api_data.get("media_url"):
        options["Stream"] = api_data["media_url"]
    elif api_data.get("direct_download_url"):
        options["Direct"] = api_data["direct_download_url"]

    return options


def get_api_file_info(share_url: str) -> dict:
    api_url = f"{TERABOX.API_DOWNLOAD_ENDPOINT}?url={quote_plus(share_url)}"
    resp = requests.get(api_url, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    data = resp.json()
    if not data.get("success"):
        raise ValueError(data.get("message") or data.get("error") or "API download failed")

    download_options = get_api_download_options(data)
    download_link = get_api_download_url(data)
    if not download_options and not download_link:
        raise ValueError("API response did not include a downloadable link")

    size_bytes = int(data.get("size") or 0)
    return {
        "name": clean_filename(data.get("filename") or "download"),
        "download_link": download_link,
        "download_options": download_options,
        "best_quality": data.get("best_quality"),
        "size_bytes": size_bytes,
        "size_str": get_size(size_bytes),
        "resolved_url": data.get("resolved_url") or share_url,
        "original_url": share_url,
        "source": "api",
    }

def get_stream_link_info(stream_url: str) -> dict:
    filename = clean_filename(urlparse(stream_url).path.rsplit("/", 1)[-1] or "download")
    return {
        "name": filename,
        "download_link": stream_url,
        "size_bytes": 0,
        "size_str": get_size(0),
        "resolved_url": stream_url,
        "original_url": stream_url,
        "source": "stream",
    }

def find_between(text: str, start: str, end: str) -> str:
    try:
        return text.split(start, 1)[1].split(end, 1)[0]
    except Exception:
        return ""

def get_file_info(share_url: str) -> dict:
    resp = requests.get(share_url, headers=HEADERS, allow_redirects=True, timeout=REQUEST_TIMEOUT)
    if resp.status_code != 200:
        raise ValueError(f"Failed to fetch share page ({resp.status_code})")
    final_url = resp.url

    parsed = urlparse(final_url)
    surl = parse_qs(parsed.query).get("surl", [None])[0]
    if not surl:
        raise ValueError("Invalid share URL (missing surl)")

    page = requests.get(final_url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
    html = page.text

    js_token = find_between(html, 'fn%28%22', '%22%29')
    logid = find_between(html, 'dp-logid=', '&')
    bdstoken = find_between(html, 'bdstoken":"', '"')
    if not all([js_token, logid, bdstoken]):
        raise ValueError("Failed to extract authentication tokens")

    params = {
        "app_id": "250528", "web": "1", "channel": "dubox",
        "clienttype": "0", "jsToken": js_token, "dp-logid": logid,
        "page": "1", "num": "20", "by": "name", "order": "asc",
        "site_referer": final_url, "shorturl": surl, "root": "1,",
    }
    info = requests.get(
        "https://www.terabox.app/share/list?" + urlencode(params),
        headers=HEADERS,
        timeout=REQUEST_TIMEOUT
    ).json()

    if info.get("errno") or not info.get("list"):
        errmsg = info.get("errmsg", "Unknown error")
        raise ValueError(f"List API error: {errmsg}")

    file = info["list"][0]
    size_bytes = int(file.get("size", 0))
    return {
        "name": file.get("server_filename", "download"),
        "download_link": file.get("dlink", ""),
        "size_bytes": size_bytes,
        "size_str": get_size(size_bytes),
        "resolved_url": share_url,
        "original_url": share_url,
        "source": "scraper",
    }


def get_download_info(url: str) -> dict:
    if re.match(API_DOWNLOAD_REGEX, url):
        return get_stream_link_info(url)

    if TERABOX.USE_API_DOWNLOAD:
        try:
            return get_api_file_info(url)
        except Exception:
            if not TERABOX.API_FALLBACK_TO_SCRAPER:
                raise

    return get_file_info(url)


def get_cache_keys(info: dict) -> list:
    keys = [
        info.get("original_url"),
        info.get("resolved_url"),
        info.get("download_link"),
    ]
    return list(dict.fromkeys(key for key in keys if key))


def get_cached_upload(info: dict):
    keys = get_cache_keys(info)
    if not keys:
        return None
    return last_upload_col.find_one({"keys": {"$in": keys}, "file_id": {"$exists": True}})


def save_cached_upload(info: dict, file_id: str):
    if not file_id:
        return

    keys = get_cache_keys(info)
    if not keys:
        return

    now = datetime.utcnow()
    cached = last_upload_col.find_one({"keys": {"$in": keys}})
    cache_data = {
        "file_id": file_id,
        "file_name": info.get("name", "download"),
        "size_str": info.get("size_str", get_size(0)),
        "resolved_url": info.get("resolved_url"),
        "updated_at": now,
    }

    if cached:
        last_upload_col.update_one(
            {"_id": cached["_id"]},
            {"$set": cache_data, "$addToSet": {"keys": {"$each": keys}}}
        )
        return

    cache_data["keys"] = keys
    cache_data["created_at"] = now
    last_upload_col.insert_one(cache_data)


async def _delete_later(msg, delay: int):
    await asyncio.sleep(delay)
    try:
        await msg.delete()
    except Exception:
        pass


def schedule_delete(msg, delay: int = AUTO_DELETE_SECONDS):
    # Run in the background so the handler (and its worker) is released immediately
    task = asyncio.create_task(_delete_later(msg, delay))
    PENDING_DELETES.add(task)
    task.add_done_callback(PENDING_DELETES.discard)
    return task


def extract_url(text: str) -> str:
    match = re.search(TERABOX_REGEX, text or "")
    return match.group(0) if match else (text or "").strip()


def build_caption(info: dict, fallback_url: str) -> str:
    return (
        f"File Name: {info['name']}\n"
        f"File Size: {info['size_str']}\n"
        f"Link: {info.get('resolved_url', fallback_url)}"
    )


async def send_cached_upload(client, message: Message, cached: dict, info: dict) -> bool:
    file_id = cached.get("file_id")
    if not file_id:
        return False

    info = info.copy()
    info["name"] = cached.get("file_name") or info.get("name", "download")
    info["size_str"] = cached.get("size_str") or info.get("size_str", get_size(0))
    caption = build_caption(info, (message.text or "").strip())

    await message.reply("♻️ File found in cache. Sending without downloading again...")

    try:
        if CHANNEL.ID:
            await client.send_document(
                chat_id=CHANNEL.ID,
                document=file_id,
                caption=caption,
                file_name=info["name"]
            )

        sent_msg = await client.send_document(
            chat_id=message.chat.id,
            document=file_id,
            caption=caption,
            file_name=info["name"],
            protect_content=True
        )
    except Exception:
        return False

    await message.reply("✅ Cached file will be deleted from your chat after 12 hours.")
    schedule_delete(sent_msg)
    return True


def build_quality_buttons(selection_id: str, info: dict) -> InlineKeyboardMarkup:
    buttons = []
    best_quality = info.get("best_quality")
    for quality in info.get("download_options", {}):
        label = f"{quality} ⭐" if quality == best_quality else quality
        buttons.append([InlineKeyboardButton(label, callback_data=f"tera_dl:{selection_id}:{quality}")])
    return InlineKeyboardMarkup(buttons)


def purge_expired_selections():
    now = asyncio.get_event_loop().time()
    for selection_id, selection in list(QUALITY_SELECTIONS.items()):
        if selection["expires_at"] < now:
            QUALITY_SELECTIONS.pop(selection_id, None)


def cache_quality_selection(user_id: int, info: dict) -> str:
    purge_expired_selections()
    selection_id = uuid4().hex[:12]
    QUALITY_SELECTIONS[selection_id] = {
        "user_id": user_id,
        "info": info,
        "expires_at": asyncio.get_event_loop().time() + QUALITY_SELECTION_TTL,
    }
    return selection_id


def get_cached_quality_selection(selection_id: str, user_id: int):
    selection = QUALITY_SELECTIONS.get(selection_id)
    now = asyncio.get_event_loop().time()
    if not selection or selection["expires_at"] < now:
        QUALITY_SELECTIONS.pop(selection_id, None)
        return None
    if selection["user_id"] != user_id:
        return None
    return selection


def download_file(download_link: str, fallback_name: str, dest_dir: str):
    with requests.get(download_link, headers=DL_HEADERS, stream=True, timeout=REQUEST_TIMEOUT) as r:
        r.raise_for_status()
        name = filename_from_response(r, fallback_name)
        path = os.path.join(dest_dir, name)
        with open(path, "wb") as f:
            # iter_content decodes gzip/deflate transfer encodings, unlike r.raw
            for chunk in r.iter_content(chunk_size=DOWNLOAD_CHUNK_SIZE):
                if chunk:
                    f.write(chunk)
    return name, path


async def download_and_upload(client, message: Message, info: dict):
    await message.reply("📥 Downloading...")
    temp_dir = tempfile.mkdtemp(prefix="terabox_")

    try:
        # Blocking HTTP runs in a thread so the bot keeps serving other users
        info["name"], temp_path = await asyncio.to_thread(
            download_file, info["download_link"], info["name"], temp_dir
        )

        caption = build_caption(info, (message.text or "").strip())

        if CHANNEL.ID:
            await client.send_document(
                chat_id=CHANNEL.ID,
                document=temp_path,
                caption=caption,
                file_name=info["name"]
            )

        sent_msg = await client.send_document(
            chat_id=message.chat.id,
            document=temp_path,
            caption=caption,
            file_name=info["name"],
            protect_content=True
        )

        if sent_msg.document:
            await asyncio.to_thread(save_cached_upload, info, sent_msg.document.file_id)

        await message.reply("✅ File will be deleted from your chat after 12 hours.")
        schedule_delete(sent_msg)

    except Exception as e:
        await message.reply(f"❌ Upload failed:\n`{e}`")
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


@Client.on_message(filters.private & filters.regex(TERABOX_REGEX))
async def handle_terabox(client, message: Message):
    user_id = message.from_user.id

    if IS_VERIFY and not await is_verified(user_id):
        verify_url = await build_verification_link(client.me.username, user_id)
        buttons = [
            [
                InlineKeyboardButton("✅ Verify Now", url=verify_url),
                InlineKeyboardButton("📖 Tutorial", url=HOW_TO_VERIFY)
            ]
        ]
        await message.reply_text(
            "🔐 You must verify before using this command.\n\n⏳ Verification lasts for 12 hours.",
            reply_markup=InlineKeyboardMarkup(buttons)
        )
        return

    url = extract_url(message.text)
    cached = await asyncio.to_thread(
        get_cached_upload, {"original_url": url, "resolved_url": url, "download_link": url}
    )
    cached_info = {
        "name": cached.get("file_name", "download") if cached else "download",
        "size_str": cached.get("size_str", get_size(0)) if cached else get_size(0),
        "resolved_url": cached.get("resolved_url") or url if cached else url,
    }
    if cached and await send_cached_upload(client, message, cached, cached_info):
        return

    try:
        info = await asyncio.to_thread(get_download_info, url)
    except Exception as e:
        return await message.reply(f"❌ Failed to get file info:\n{e}")

    cached = await asyncio.to_thread(get_cached_upload, info)
    if cached and await send_cached_upload(client, message, cached, info):
        return

    download_options = info.get("download_options") or {}
    if len(download_options) > 1:
        selection_id = cache_quality_selection(user_id, info)
        await message.reply(
            f"🎞 Select download quality for `{info['name']}`:",
            reply_markup=build_quality_buttons(selection_id, info)
        )
        return

    if download_options:
        info["download_link"] = next(iter(download_options.values()))

    await download_and_upload(client, message, info)


@Client.on_callback_query(filters.regex(r"^tera_dl:"))
async def handle_quality_selection(client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    try:
        _, selection_id, quality = callback_query.data.split(":", 2)
    except ValueError:
        return await callback_query.answer("Invalid selection.", show_alert=True)

    selection = get_cached_quality_selection(selection_id, user_id)
    if not selection:
        return await callback_query.answer("This quality selection expired. Send the link again.", show_alert=True)

    info = selection["info"].copy()
    download_url = info.get("download_options", {}).get(quality)
    if not download_url:
        return await callback_query.answer("Selected quality is unavailable.", show_alert=True)

    QUALITY_SELECTIONS.pop(selection_id, None)
    info["download_link"] = download_url
    await callback_query.answer(f"Selected {quality}")
    await callback_query.message.edit_reply_markup(reply_markup=None)

    cached = await asyncio.to_thread(get_cached_upload, info)
    if cached and await send_cached_upload(client, callback_query.message, cached, info):
        return

    await download_and_upload(client, callback_query.message, info)
