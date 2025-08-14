# bot.py - Auto-detect Telethon join handler, cleaned URLs, safer defaults
from telethon import TelegramClient, events
from telethon.tl import types
from pymongo import MongoClient
import logging, os, asyncio, io
from datetime import datetime, timezone

# Try to load audio analysis (pydub)
try:
    from pydub import AudioSegment
    HAS_AUDIO = True
except Exception as e:
    HAS_AUDIO = False
    logging.warning(f"pydub not available: {e}")

# ---------------- Logging ----------------
logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ---------------- Config ----------------
class Config:
    API_ID = int(os.getenv("API_ID"))
    API_HASH = os.getenv("API_HASH")
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    MONGO_URL = os.getenv("MONGO_URL")
    GROUP_ID = int(os.getenv("GROUP_ID"))
    TOPIC_ID = int(os.getenv("TOPIC_ID"))
    VOICE_PENDING_TIMEOUT = int(os.getenv("VOICE_PENDING_TIMEOUT", "7200"))  # 2h

# ---------------- Database ----------------
mongo = MongoClient(Config.MONGO_URL)
db = mongo["noveltamiz"]
pending = db["pending"]

# ---------------- Bot Client ----------------
bot = TelegramClient("bot", Config.API_ID, Config.API_HASH)

# ---------------- Messages ----------------
WELCOME_MSG = (
    "👋 வணக்கம்! தயவுசெய்து உங்கள் அறிமுக குரல் செய்தியை அனுப்பவும்.\n"
    "✅ 5 வினாடிகளுக்கு மேல் இருக்க வேண்டும்.\n"
    "🚫 மிகக் குறுகியவை நிராகரிக்கப்படும்."
)

APPROVED_MSG = (
    "✅ உங்கள் கோரிக்கை ஒப்புதல் பெற்றது!\n"
    "🎉 வரவேற்கிறோம்!\n\n"
    "👉 இங்கே செல்லவும்: https://t.me/c/{group_id_part}/{topic_id}"
)

# ---------------- Voice Analysis ----------------
async def analyze_voice(file_bytes: bytes) -> bool:
    if not HAS_AUDIO:
        return True  # Skip if pydub unavailable
    try:
        audio = AudioSegment.from_file(io.BytesIO(file_bytes), format="ogg")
        return len(audio) >= 5000  # at least 5 sec
    except Exception as e:
        logger.error(f"Voice analysis failed: {e}")
        return False

# ---------------- Handlers ----------------
def register_handlers():
    group_id_part = str(Config.GROUP_ID)[4:] if str(Config.GROUP_ID).startswith("-100") else str(Config.GROUP_ID)

    if hasattr(events, "ChatJoinRequest"):
        logger.info("🚀 Using ChatJoinRequest handler (Telethon >= 1.40)")

        @bot.on(events.ChatJoinRequest)
        async def join_request_handler(event):
            if event.chat_id != Config.GROUP_ID:
                return
            user = await event.get_user()
            await event.approve()
            try:
                await bot.send_message(user.id, WELCOME_MSG)
                pending.insert_one({
                    "user_id": user.id,
                    "request_time": datetime.now(timezone.utc).isoformat(),
                    "status": "awaiting_voice"
                })
            except Exception as e:
                logger.error(f"Failed to DM user {user.id}: {e}")

    else:
        logger.info("🔧 Using ChatActionRequestedJoin fallback (Telethon 1.24–1.39)")

        @bot.on(events.ChatAction(func=lambda e: isinstance(e.action, types.ChatActionRequestedJoin)))
        async def join_request_handler(event):
            if event.chat_id != Config.GROUP_ID:
                return
            user = await event.get_user()
            # Approve user
            await bot.edit_permissions(Config.GROUP_ID, user.id, view_messages=True)
            try:
                await bot.send_message(user.id, WELCOME_MSG)
                pending.insert_one({
                    "user_id": user.id,
                    "request_time": datetime.now(timezone.utc).isoformat(),
                    "status": "awaiting_voice"
                })
            except Exception as e:
                logger.error(f"Failed to DM user {user.id}: {e}")

    # Handle voice note in DM
    @bot.on(events.NewMessage(incoming=True, func=lambda e: e.is_private and e.voice))
    async def voice_handler(event):
        user_id = event.sender_id
        record = pending.find_one({"user_id": user_id})
        if not record:
            return
        file = await event.download_media(bytes)
        ok = await analyze_voice(file)
        if ok:
            pending.delete_one({"user_id": user_id})
            await event.reply("🎉 குரல் சரிபார்ப்பு வெற்றி! வரவேற்கிறோம்.")
            # Optionally send approved message with link
            await event.reply(APPROVED_MSG.format(group_id_part=group_id_part, topic_id=Config.TOPIC_ID))
        else:
            await event.reply("❌ குரல் குறுகியது அல்லது செல்லாதது. மீண்டும் முயற்சிக்கவும்.")

# ---------------- Main ----------------
async def main():
    if not HAS_AUDIO:
        logger.warning("🔇 Audio analysis disabled: pydub/ffmpeg not available")
    await bot.start(bot_token=Config.BOT_TOKEN)
    register_handlers()
    logger.info("🤖 Bot started. Awaiting events...")
    await bot.run_until_disconnected()

if __name__ == "__main__":
    import nest_asyncio
    nest_asyncio.apply()
    import asyncio
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())