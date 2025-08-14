# bot.py - @NovelsTamilGuardBot
# Voice verification bot for existing & new members
from telethon import TelegramClient, events
from telethon.tl.custom import Button
from pymongo import MongoClient
from pydub import AudioSegment
import io, os, asyncio, logging
from datetime import datetime, timezone, timedelta
from config import Config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = TelegramClient('guard_bot', Config.API_ID, Config.API_HASH)
db = MongoClient(Config.MONGO_URI).guard_bot
pending_col = db.pending_applications  # user_id, status, voice_msg_id, etc.

# Messages
WELCOME_MSG = """👋 வணக்கம், {name}!

நீங்கள் **Tamil Novels** குழுவில் சேர விண்ணப்பித்துள்ளீர்கள்.

✅ சேர பெயர், பாலினம் மற்றும் எங்கு இந்த குழு இணைப்பு லிங்கை பெற்றீர்கள், மற்றும் ஏன் சேர விரும்புகிறீர்கள்? என்பதை ஒரு **குரல் பதிவு (Voice Note)** அனுப்பவும்.
🚫 பொருத்தமற்றவை நிராகரிக்கப்படும்.
⏱️ 2 மணி நேரத்துக்குள் அனுப்பவில்லை என்றால் விண்ணப்பம் தானாக நிராகரிக்கப்படும்."""

REMINDER_MSG = """⏰ வணக்கம், {name}!

நீங்கள் குரல் காட்சி அனுப்பவில்லை. இன்னும் **2 மணி நேரம்** உங்களுக்கு உள்ளது.

உடனே அனுப்பவும், இல்லையெனில் உங்கள் விண்ணப்பம் தானாக நிராகரிக்கப்படும்."""

APPROVED_MSG = """🎉 வாழ்த்துகள்! நீங்கள் குழுவில் சேர்க்கப்பட்டுள்ளீர்கள்!
👉 இங்கே செல்லவும்: https://t.me/c/{group_id_part}/{topic_id}"""

REJECTED_MSG = """❌ உங்கள் விண்ணப்பம் நிராகரிக்கப்பட்டது."""

# Helper
def esc(s):
    s = str(s) if s else "N/A"
    for c in r'\_*[]()~`>#+-=|{}.!':
        s = s.replace(c, f'\\{c}')
    return s

async def log_mod(text):
    try:
        await bot.send_message(Config.MODLOG_GROUP_ID, text, parse_mode='markdown')
    except Exception as e:
        logger.warning(f"Failed to log: {e}")

# --- Voice Analysis Functions ---
def is_too_short(audio_data, min_duration=3000):  # 3 sec
    try:
        audio = AudioSegment.from_file(io.BytesIO(audio_data), format="ogg")
        return len(audio) < min_duration
    except:
        return True

def is_silence(audio_data, silence_threshold=-50.0):
    try:
        audio = AudioSegment.from_file(io.BytesIO(audio_data), format="ogg")
        return audio.dBFS < silence_threshold
    except:
        return True

def is_robotic_tts(audio_data):
    try:
        audio = AudioSegment.from_file(io.BytesIO(audio_data), format="ogg")
        chunks = [chunk.dBFS for chunk in audio[::1000] if chunk.dBFS > -100]
        if len(chunks) < 2:
            return True
        variance = sum(abs(chunks[i] - chunks[i-1]) for i in range(1, len(chunks))) / len(chunks)
        return variance < 2.0  # Low variation = likely robotic
    except:
        return True

# --- Deep Link Handler ---
@bot.on(events.NewMessage(pattern='/start'))
async def start(event):
    args = event.message.message.split(" ")[1:]
    if args and args[0].startswith("approve_"):
        user_id = args[0].split("_")[1]
        if event.sender_id in Config.ADMINS:
            await event.respond(f"✅ Shortcut: Approve user `{user_id}`", buttons=[
                [Button.inline("✅ Approve", data=f"approve_{user_id}_0")],
                [Button.inline("❌ Reject", data=f"reject_{user_id}_0")]
            ])
        else:
            await event.respond("🚫 உங்களுக்கு அனுமதி இல்லை.")
        await event.delete()
        return

    if event.is_private:
        await event.respond("🛡️ இந்த போட் குழு சேர்வு செயல்முறைக்கானது. நீங்கள் சேர விண்ணப்பித்தால், உங்களுக்கு செய்தி அனுப்பப்படும்.")
    await event.delete()

# --- Handle Join Request ---
@bot.on(events.ChatAction(func=lambda e: e.user_requested_to_join))
async def handle_join_request(event):
    user = await event.get_user()
    pending_col.update_one(
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
        msg = await bot.send_message(user.id, WELCOME_MSG.format(name=esc(user.first_name)))
        logger.info(f"Sent welcome to {user.id}")

        # Schedule 24h reminder
        asyncio.create_task(reminder_task(user.id, user.first_name))

        # --- Log to Mod Group (MOVED INSIDE THE TRY BLOCK) ---
        group_id_part = str(Config.GROUP_ID)[4:]
        topic_link = (
            f"[👉 Go to Topic](https://t.me/c/{group_id_part}/{Config.TOPIC_ID})" # Fixed space
            if Config.TOPIC_ID
            else "N/A"
        )

        await log_mod(
            f"*Join Request Received*\n"
            f"• Name: [{esc(user.first_name)}](tg://user?id={user.id})\n"
            f"• Username: @{user.username}\n"
            f"• ID: `{user.id}`\n"
            f"• Status: Awaiting voice note\n"
            f"{topic_link}",
            parse_mode='markdown'
        )
        # --- End of Logging ---
    except Exception as e:
        await log_mod(f"❌ Failed to DM applicant {user.id}: {e}")
        # Don't return here, let the function end naturally or handle as needed
        # If you want to stop processing on DM failure, `return` is okay, but
        # ensure the log_mod outside the try isn't executed.
        return # This is fine if you intend to stop on DM error

    # Code here would run only if the try block succeeded completely.
    # Since we moved the logging inside, there's nothing else needed here
    # for this specific logic flow.

# --- 24-Hour Reminder ---
async def reminder_task(user_id, name):
    await asyncio.sleep(Config.VOICE_PENDING_TIMEOUT)
    record = pending_col.find_one({"user_id": user_id, "status": "pending"})
    if record:
        try:
            await bot.send_message(user_id, REMINDER_MSG.format(name=esc(name)))
            logger.info(f"Sent 24h reminder to {user_id}")
        except Exception as e:
            logger.warning(f"Failed to send reminder to {user_id}: {e}")

# --- Handle Voice Note ---
@bot.on(events.NewMessage(incoming=True, func=lambda e: e.is_private and e.voice))
async def handle_voice(event):
    user = await event.get_user()
    record = pending_col.find_one({"user_id": user.id, "status": "pending"})
    if not record:
        return

    voice_data = await event.download_media(bytes)

    # Analyze voice
    issues = []
    if is_too_short(voice_data):
        issues.append("⚠️ Too short (<3s)")
    if is_silence(voice_data):
        issues.append("⚠️ Silence detected")
    if is_robotic_tts(voice_data):
        issues.append("⚠️ Robotic/TTS-like voice")

    # Forward to mod group
    msg = await event.forward_to(Config.MODLOG_GROUP_ID)

    status = "🚩 Suspicious" if issues else "🎤 Valid"
    caption = f"*{status}* - {esc(user.first_name)}\n• ID: `{user.id}`"
    if issues:
        caption += "\n" + "\n".join(issues)

    buttons = [
        [Button.inline("✅ Approve", data=f"approve_{user.id}_{msg.id}"),
         Button.inline("❌ Reject", data=f"reject_{user.id}_{msg.id}")]
    ]

    await bot.send_message(
        Config.MODLOG_GROUP_ID,
        caption,
        buttons=buttons,
        parse_mode='markdown'
    )

    # Reply to user
    if issues:
        await event.reply("❌ உங்கள் குரல் பதிவு சந்தேகத்திற்குரியதாக உள்ளது. தெளிவான குரலில் மீண்டும் அனுப்பவும்.")
    else:
        await event.reply("✅ குரல் பதிவு பெறப்பட்டது. நிர்வாகி விரைவில் பதிலளிப்பார்.")

    pending_col.update_one(
        {"user_id": user.id},
        {"$set": {"status": "voice_sent", "voice_msg_id": msg.id}}
    )

# --- Handle Approval ---
@bot.on(events.CallbackQuery(data=re.compile(b'^(approve|reject)_(\\d+)_?(\\d+)?')))
async def handle_approval(event):
    action = event.data_match.group(1).decode()
    user_id = int(event.data_match.group(2))
    msg_id = int(event.data_match.group(3) or 0)

    if event.sender_id not in Config.ADMINS:
        return await event.answer("🚫 உங்களுக்கு அனுமதி இல்லை.")

    try:
        user = await bot.get_entity(user_id)
        name = esc(user.first_name)
        group_id_part = str(Config.GROUP_ID)[4:]

        if action == "approve":
            await bot.edit_permissions(Config.GROUP_ID, user_id, view_messages=True)
            await bot.send_message(user_id, APPROVED_MSG.format(name=name, group_id_part=group_id_part, topic_id=Config.TOPIC_ID))
            pending_col.update_one({"user_id": user.id}, {"$set": {"status": "approved"}})
            status_msg = "✅ Approved"
        else:
            await bot.send_message(user_id, REJECTED_MSG)
            pending_col.update_one({"user_id": user.id}, {"$set": {"status": "rejected"}})
            status_msg = "❌ Rejected"

        await event.edit(f"{status_msg} by {event.sender_id}")
        await log_mod(f"✅ Action taken: {status_msg} `{user_id}` — {name}")

    except Exception as e:
        await event.edit(f"❌ Failed: {e}")
        logger.error(f"Approval failed: {e}")

# --- Start Bot ---
async def main():
    await bot.start(bot_token=Config.BOT_TOKEN)
    logger.info("🛡️ NovelsTamilGuardBot is running...")
    await bot.run_until_disconnected()

if __name__ == '__main__':
    import nest_asyncio
    nest_asyncio.apply()
    import asyncio
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())