import logging
import threading
from flask import Flask
from pyrogram import Client
from config import BOT, API, OWNER, WEB


logging.getLogger().setLevel(logging.INFO)
logging.getLogger("pyrogram").setLevel(logging.ERROR)

app = Flask(__name__)

@app.route('/')
def home():
    return "MnBot is running!"

def run_flask():
    app.run(host='0.0.0.0', port=WEB.PORT)

class MN_Bot(Client):
    def __init__(self):
        super().__init__(
            "MN-Bot",
            api_id=API.ID,
            api_hash=API.HASH,
            bot_token=BOT.TOKEN,
            plugins=dict(root="plugins"),
            workers=16,
        )

    async def start(self):
        await super().start()
        me = await self.get_me()
        BOT.USERNAME = f"@{me.username}"
        self.mention = me.mention
        self.username = me.username
        try:
            await self.send_message(chat_id=OWNER.ID,
                                    text=f"{me.first_name} ✅✅ BOT started successfully ✅✅")
        except Exception as e:
            logging.warning(f"Could not notify owner ({OWNER.ID}): {e}")
        logging.info(f"✅ {me.first_name} BOT started successfully")

    async def stop(self, *args):
        await super().stop()
        logging.info("Bot Stopped 🙄")

if __name__ == "__main__":
    threading.Thread(target=run_flask, daemon=True).start()
    MN_Bot().run()
