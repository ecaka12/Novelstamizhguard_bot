# bot.py - @novelstamizhguard_bot
# Voice verification bot for Tamil Novels group
# Uses deep link + ChatAction fallback

import os, io, asyncio, logging
from datetime import datetime, timezone
from telethon import TelegramClient, events
from telethon.tl import types
from pymongo import MongoClient

# Optional audio analysis
try:
    from pydub import AudioSegment
    HAS_AUDIO = True
except ImportError:
    HAS_AUDIO = False

# ---------------- Logging ----------------
logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ---------------- Load Config ----------------
class Config:
    API_ID = int(os.getenv("API_ID"))
    API_HASH = os.getenv("API_HASH")
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    MONGO_URI = os.getenv("MONGO_URI")
    GROUP_ID = int(os.getenv("GROUP_ID"))  # -100...
    TOPIC_ID = int(os.getenv("TOPIC_ID", "0"))
    MODLOG_CHAT = int(os.getenv("MODLOG_CHAT"))
    ADMINS = [int(x) for x in os.getenv("ADMINS", "").split(",") if x.strip()]
    TIMEOUT = int(os.getenv("TIMEOUT", "7200"))

# ---------------- Database ----------------
mongo = MongoClient(Config.MONGO_URI)
db = mongo.guard_bot
pending = db.pending_applications

# ---------------- Bot Client ----------------
bot = TelegramClient('guard_bot', Config.API_ID, Config.API_HASH)

# ---------------- Messages ----------------
WELCOME_MSG = (
    "👋 வணக்கம், {name}!\n\n"
    "நீங்கள் **Tamil Novels** குழுவில் சேர விண்ணப்பித்துள்ளீர்கள்.\n\n"
    "✅ சேர பின்வரும் தகவல்களை ஒரு **குரல் பதிவு** அனுப்பவும்:\n"
    "1. உங்கள் பெயர், பாலினம்\n"
    "2. எங்கு இந்த லிங்கை பெற்றீர்கள்?\n"
    "3. ஏன் சேர விரும்புகிறீர்கள்?\n\n"
    "🎙️ குரல் பதிவு 5 வினாடிகளுக்கு மேல் இருக்க வேண்டும்.\n"
    "⏱️ 2 மணி நேரத்துக்குள் அனுப்பவில்லை என்றால் தானாக நிராகரிக்கப்படும்."
)

REMINDER_MSG = (
    "⏰ வணக்கம், {name}!\n\n"
    "இன்னும் **2 மணி நேரம்** உங்களுக்கு உள்ளது.\n"
    "உடனே குரல் பதிவு அனுப்பவும், இல்லையெனில் உங்கள் விண்ணப்பம் நிராகரிக்கப்படும்."
)

APPROVED_MSG = (
    "🎉 வாழ்த்துகள்! நீங்கள் குழுவில் சேர்க்கப்பட்டுள்ளீர்கள்!\n\n"
    "📌 உங்கள் சந்தா மூலம் எங்களை ஆதரிக்கலாம்: @TamilNovelsPremium\n"
    "🎁 புதிய அம்சங்கள்: கதை ஆல்பங்கள், பரிசு தொகுப்புகள், செக் லிஸ்டுகள்!\n\n"
    "👉 இங்கே செல்லவும்: https://t.me/c/{group_id_part}/{topic_id}"
)

REJECTED_MSG = "❌ உங்கள் விண்ணப்பம் நிராகரிக்கப்பட்டது."

JOIN_LINK = "https://t.me/+_1n657JUXHIzODk1"  # Your group invite link

# ---------------- Helpers ----------------
def esc(s):
    s = str(s) if s else "N/A"
    for c in r'\_*[]()~`>#+-=|{}.!':
        s = s.replace(c, f'\\{c}')
    return s

async def log_mod(text):
    try:
        await bot.send_message(Config.MODLOG_CHAT, text, parse_mode='markdown')
    except Exception as e:
        logger.warning(f"Failed to log: {e}")

# ---------------- Voice Analysis ----------------
def is_valid_voice(audio_data):
    if not HAS_AUDIO:
        return True
    try:
        audio = AudioSegment.from_file(io.BytesIO(audio_data), format="ogg")
        too_short = len(audio) < 4000
        too_quiet = audio.dBFS < -50
        return not (too_short or too_quiet)
    except Exception as e:
        logger.warning(f"Audio analysis failed: {e}")
        return False

# ---------------- Handlers ----------------
async def start_bot():
    await bot.start(bot_token=Config.BOT_TOKEN)
    logger.info("🛡️ Bot started. Registering handlers...")

    # Auto-detect handler
    if hasattr(events, 'ChatJoinRequest'):
        logger.info("🚀 Using ChatJoinRequest (Telethon >= 1.40)")

        @bot.on(events.ChatJoinRequest)
        async def handler(event):
            if event.chat_id != Config.GROUP_ID:
                return
            user = await event.get_user()
            await handle_join_request(user, event)

    else:
        logger.info("🔧 Using ChatActionRequestedJoin fallback")

        @bot.on(events.ChatAction(func=lambda e: 
            isinstance(e.action, types.ChatActionRequestedJoin) and e.chat_id == Config.GROUP_ID))
        async def handler(event):
            user = await event.get_user()
            await handle_join_request(user, event)

    # Handle voice in DM
    @bot.on(events.NewMessage(incoming=True, func=lambda e: e.is_private and e.voice))
    async def voice_handler(event):
        user = await event.get_user()
        record = pending.find_one({"user_id": user.id, "status": "pending"})
        if not record:
            return

        voice_data = await event.download_media(bytes)
        if not is_valid_voice(voice_data):
            await event.reply("❌ குரல் பதிவு மிகக் குறுகியது அல்லது தெளிவற்றது. மீண்டும் அனுப்பவும்.")
            return

        msg = await event.forward_to(Config.MODLOG_CHAT)
        await event.reply("✅ குரல் பதிவு பெறப்பட்டது. நிர்வாகி விரைவில் பதிலளிப்பார்.")
        pending.update_one({"user_id": user.id}, {"$set": {"status": "voice_sent", "msg_id": msg.id}})

        # Notify mods
        await bot.send_message(
            Config.MODLOG_CHAT,
            f"🎤 Valid voice from {esc(user.first_name)} (`{user.id}`)",
            buttons=[
                [Button.inline("✅ Approve", data=f"approve_{user.id}"),
                 Button.inline("❌ Reject", data=f"reject_{user.id}")]
            ],
            parse_mode='markdown'
        )

    # Approval callback
    @bot.on(events.CallbackQuery(pattern=r"^(approve|reject)_(\d+)$"))
    async def approve_handler(event):
        if event.sender_id not in Config.ADMINS:
            return await event.answer("🚫 உங்களுக்கு அனுமதி இல்லை.")

        action, user_id = event.data.decode().split("_")
        user_id = int(user_id)
        user = await bot.get_entity(user_id)

        if action == "approve":
            await bot.edit_permissions(Config.GROUP_ID, user_id, view_messages=True)
            group_id_part = str(Config.GROUP_ID)[4:]
            await bot.send_message(user_id, APPROVED_MSG.format(
                name=esc(user.first_name),
                group_id_part=group_id_part,
                topic_id=Config.TOPIC_ID
            ))
            pending.update_one({"user_id": user_id}, {"$set": {"status": "approved"}})
            await event.edit("✅ Approved")
        else:
            await bot.send_message(user_id, REJECTED_MSG)
            pending.update_one({"user_id": user_id}, {"$set": {"status": "rejected"}})
            await event.edit("❌ Rejected")

    # Start command
    @bot.on(events.NewMessage(pattern='/start'))
    async def start(event):
        if event.is_private:
            # Check for deep link
            if event.message.message == "/start join":
                await event.reply(
                    "👋 வணக்கம்! நீங்கள் தயாராக உள்ளீர்கள்.\n\n"
                    "பின்னர் குழுவில் சேர விண்ணப்பிக்கவும்:\n"
                    f"{JOIN_LINK}\n\n"
                    "நிர்வாகி உங்கள் குரல் பதிவை சரிபார்ப்பார்.",
                    buttons=[[Button.url("🔗 குழுவில் சேரவும்", JOIN_LINK)]]
                )
            else:
                await event.reply(
                    "🛡️ வணக்கம்! நீங்கள் இந்த போட்டை தொடங்கியுள்ளீர்கள்.\n\n"
                    "குழுவில் சேர, பின்வரும் இணைப்பைப் பயன்படுத்தவும்:\n"
                    f"{JOIN_LINK}\n\n"
                    "பின்னர் ஒரு **குரல் பதிவு** அனுப்பவும்.",
                    buttons=[[Button.url("🔗 குழுவில் சேரவும்", JOIN_LINK)]]
                )
        await event.delete()

    logger.info("✅ All handlers registered. Bot is live.")
    await bot.run_until_disconnected()

async def handle_join_request(user, event):
    logger.info(f"📩 Join request from {user.id} ({user.first_name})")

    pending.update_one(
        {"user_id": user.id},
        {"$set": {
            "first_name": user.first_name,
            "username": user.username,
            "request_time": datetime.now(timezone.utc),
            "status": "pending"
        }},
        upsert=True
    )

    try:
        await bot.send_message(user.id, WELCOME_MSG.format(name=esc(user.first_name)))
        logger.info(f"✅ Sent welcome DM to {user.id}")

        # Schedule reminder
        asyncio.create_task(reminder_task(user.id, user.first_name))

        # Log to mod group
        group_id_part = str(Config.GROUP_ID)[4:]
        topic_link = f"[👉 Go to Topic](https://t.me/c/{group_id_part}/{Config.TOPIC_ID})"
        await log_mod(
            f"*📩 New Join Request*\n"
            f"• {esc(user.first_name)} (`{user.id}`)\n"
            f"• @{user.username}\n"
            f"{topic_link}",
            parse_mode='markdown'
        )

    except Exception as e:
        logger.error(f"❌ Failed to DM {user.id}: {type(e).__name__}: {e}")
        await log_mod(f"⚠️ DM failed for {user.id}: {e}")

async def reminder_task(user_id, name):
    await asyncio.sleep(Config.TIMEOUT)
    record = pending.find_one({"user_id": user_id, "status": "pending"})
    if record:
        try:
            await bot.send_message(user_id, REMINDER_MSG.format(name=esc(name)))
        except Exception as e:
            logger.warning(f"Failed to send reminder: {e}")

# ---------------- Start ----------------
if __name__ == '__main__':
    from telethon.tl.custom import Button
    import nest_asyncio
    nest_asyncio.apply()
    loop = asyncio.get_event_loop()
    loop.run_until_complete(start_bot())