


# 📦 TeraBox Downloader Telegram Bot

Download any public TeraBox file directly in Telegram with ease!

This bot allows users to paste a TeraBox file link and get the file uploaded directly to their Telegram chat and a fixed channel. No ads — just fast, clean downloads.

---

## 🚀 Features

* 🔗 Accepts public TeraBox share links
* 🧠 Automatically extracts file info (name, size, direct link)
* 🌐 Supports API-based resolving through the MN Bots TeraBox API
* 🎬 Accepts API `/dl/` stream links and downloads them directly
* 🎞 Shows quality buttons when the API returns multiple download URLs
* ♻️ Reuses cached Telegram file IDs, so previously downloaded files are sent again without re-downloading
* ⚙️ Verifies user before allowing downloads (optional, with tutorial)
* ⬇️ Downloads the file using an API stream link or direct TeraBox download link
* 📤 Uploads the file back to Telegram (both to user PM & fixed channel)
* 🔐 User uploads use **restricted forwarding** for protection
* ⏲️ Automatically deletes the user file after 12 hours to save space

---

## 📥 How To Use

1. Start the bot.
2. Send a valid TeraBox public share link or a supported API `/dl/` stream link
3. The bot will:

   * (If enabled) Ask for verification
   * Fetch file info
   * Ask you to select a quality when multiple API URLs are available
   * Re-send a cached Telegram file if it was downloaded before
   * Download and upload to Telegram only when no cache exists
   * Notify that file will be deleted in 12 hours

---

## 🛡️ Verification System (Optional)

If verification is enabled in config:

* Unverified users will get a button to verify via external URL
* Verification is valid for 12 hours
* Configurable in `verify_patch.py`

---

## 🔧 Environment Variables

Set the following environment variables in your deployment dashboard:

| Variable        | Description                                                               |
| --------------- | ------------------------------------------------------------------------- |
| `TOKEN`         | Telegram Bot Token from @BotFather                                        |
| `API_ID`        | Telegram API ID from [https://my.telegram.org](https://my.telegram.org)   |
| `API_HASH`      | Telegram API Hash from [https://my.telegram.org](https://my.telegram.org) |
| `CHANNEL_ID`    | Channel ID (starts with `-100`) where files will be uploaded              |
| `IS_VERIFY`     | (true/false) Enable user verification system                              |
| `SHORTLINK_URL` | Domain for the shortlink service (e.g., "linkshortify.com")               |
| `SHORTLINK_API` | API key for the shortlink service to shorten verification URLs             |
| `HOW_TO_VERIFY` | URL to a tutorial or guide for users on how to verify (e.g., Telegram post)|
| `OWNER`         | User ID of the bot owner for admin privileges                              |
| `PORT`          | Port number for web-related features (e.g., 8000)                          |
| `DB_URI`        | MongoDB connection URI for database access                                |
| `TERABOX_API_DOWNLOAD_ENDPOINT` | API endpoint used to resolve TeraBox share links (default: `https://terabox-api.mn-bots.workers.dev/download`) |
| `TERABOX_USE_API_DOWNLOAD` | Set to `false` to disable API-based resolving and use only the scraper |
| `TERABOX_API_FALLBACK` | Set to `false` to stop falling back to the scraper when API resolving fails |
| `TERABOX_COOKIE` | TeraBox `ndus=...` cookie used by the scraper and direct downloads (overrides the built-in default) |

---
## Important
do not forget to set your own TeraBox cookie via the `TERABOX_COOKIE` environment variable (or edit the default in `config.py`)
## 💻 Deployment

You can deploy this bot on platforms like:

* [Koyeb](https://www.koyeb.com/)
* [Render](https://render.com/)
* [Railway](https://railway.app/)

Make sure to:

* Set environment variables
* Keep MongoDB (like from [MongoDB Atlas](https://www.mongodb.com/cloud/atlas))
* Use `requirements.txt` for installing dependencies

---

## 🙋 FAQ

**Q: Where are files sent?**
A: Files are sent to your Telegram PM and also a Telegram channel.

**Q: How long are files stored?**
A: Files sent to users are deleted automatically after 12 hours.

**Q: Is verification necessary?**
A: You can disable it by setting `IS_VERIFY=false` in your config.

---

## 🤝 Credits

* Maintained by: **@mnbots**
* Uses Pyrogram, MongoDB, Python, and optional MN Bots API-based TeraBox resolving

---

## 📜 License

This project is open-source and free to use. Modify it for your own needs. Attribution appreciated.
