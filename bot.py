# bot.py - @novelstamizhguard_bot
# Voice verification bot for Tamil Novels group
# Fixed for Telethon v1.24+ | No ChatJoinRequest needed

import os, io, asyncio, logging
from datetime import datetime, timezone
from telethon import TelegramClient, events, errors
from telethon.tl import types
from telethon.tl.custom import Button
from pymongo import MongoClient

# Optional: pydub for voice analysis
try:
    from pydub import AudioSegment
    HAS_AUDIO = True
except ImportError:
    HAS_AUDIO = False
    print("Warning: pydub not found. Voice analysis disabled.")

# ---------------- Logging ----------------
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO # Consider DEBUG for troubleshooting
)
logger = logging.getLogger(__name__)

# ---------------- Config ----------------
class Config:
    API_ID = int(os.getenv("API_ID"))
    API_HASH = os.getenv("API_HASH")
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    MONGO_URI = os.getenv("MONGO_URI")
    GROUP_ID = int(os.getenv("GROUP_ID"))  # -100...
    TOPIC_ID = int(os.getenv("TOPIC_ID", "0")) # Default to 0 if not set
    MODLOG_CHAT = int(os.getenv("MODLOG_CHAT"))
    ADMINS = [int(x) for x in os.getenv("ADMINS", "").split(",") if x.strip()]
    TIMEOUT = int(os.getenv("TIMEOUT", "7200"))  # 2 hours

# ---------------- Database ----------------
try:
    mongo = MongoClient(Config.MONGO_URI)
    # Ping the server to ensure connection is active
    mongo.admin.command('ping')
    logger.info("✅ Connected to MongoDB")
    # Use your existing database (replace 'telegram_bot' if different)
    db = mongo.telegram_bot
    pending = db.pending_applications  # Collection name
    logger.info("✅ Database and collection ready")
except Exception as e:
    logger.error(f"❌ Failed to connect to MongoDB: {e}")
    exit(1) # Exit if DB connection fails

# ---------------- Bot Client ----------------
bot = TelegramClient('guard_bot', Config.API_ID, Config.API_HASH)

# ---------------- Messages ----------------
START_MSG = (
    "🛡️ வணக்கம்! நீங்கள் **Tamil Novels** குழுவில் சேர விரும்பினால், பின்வரும் படிகளை பின்பற்றவும்:\n\n"
    "1. இந்த போட்டில் ஏதேனும் ஒரு செய்தியை அனுப்பவும் (எ.கா: **Hi**)\n"
    "2. பின்னர் குழுவில் சேர விண்ணப்பிக்கவும்: https://t.me/+_1n657JUXHIzODk1  \n"
    "3. பின்னர் ஒரு **குரல் பதிவு** அனுப்பவும்.\n\n"
    "✅ இது பாதுகாப்பு செயல்முறை. நன்றி!"
)

WELCOME_MSG = (
    "👋 வணக்கம், {name}!\n\n"
    "நீங்கள் **Tamil Novels** குழுவில் சேர விண்ணப்பித்துள்ளீர்கள்.\n\n"
    "✅ சேர பின்வரும் தகவல்களை ஒரு **குரல் பதிவு** அனுப்பவும்:\n"
    "1. உங்கள் பெயர், பாலினம்\n"
    "2. எங்கு இந்த லிங்கை பெற்றீர்கள்?\n"
    "3. ஏன் சேர விரும்புகிறீர்கள்?\n\n"
    "🎙️ முக்கியம்: இந்த **குரல் பதிவை இந்த போட்டிற்கு மட்டுமே** அனுப்பவும் (தனியார் செய்தியாக).\n"
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

# ---------------- Helpers ----------------
def esc(s):
    s = str(s) if s else "N/A"
    for c in r'\_*[]()~`>#+-=|{}.!':
        s = s.replace(c, f'\\{c}')
    return s

async def log_mod(text):
    try:
        await bot.send_message(Config.MODLOG_CHAT, text, parse_mode='markdown')
        logger.info("✅ Logged to MODLOG_CHAT")
    except Exception as e:
        logger.warning(f"⚠️ Failed to log to MODLOG_CHAT: {e}")

# ---------------- Voice Analysis ----------------
def is_valid_voice(audio_data):
    if not HAS_AUDIO:
        logger.info("ℹ️ Skipping voice analysis (pydub not available)")
        return True # Accept if analysis is disabled
    try:
        audio = AudioSegment.from_file(io.BytesIO(audio_data), format="ogg")
        duration_ms = len(audio)
        loudness = audio.dBFS
        logger.debug(f"🔊 Voice note analysis - Duration: {duration_ms}ms, Loudness: {loudness}dBFS")
        too_short = duration_ms < 4000 # Less than 4 seconds
        too_quiet = loudness < -50 # Too quiet (dBFS is negative, -50 is quite low)
        is_valid = not (too_short or too_quiet)
        if not is_valid:
            logger.info(f"❌ Voice note rejected - Too short: {too_short}, Too quiet: {too_quiet}")
        return is_valid
    except Exception as e:
        logger.warning(f"⚠️ Audio analysis failed: {e}. Treating as invalid.")
        return False # Reject on analysis error

# ---------------- Handlers ----------------
async def start_bot():
    await bot.start(bot_token=Config.BOT_TOKEN)
    logger.info("🛡️ Bot started. Registering handlers...")

    # Handle voice notes in DM
    @bot.on(events.NewMessage(incoming=True, func=lambda e: e.is_private and e.voice))
    async def voice_handler(event):
        user = await event.get_sender()
        if not user:
            logger.warning("❌ Could not get sender from voice message")
            return

        logger.info(f"🎤 Received voice note from user {user.id} ({user.first_name})")
        logger.info(f"🔍 Checking for pending application for user {user.id}")

        # Check if user has a pending application
        record = pending.find_one({"user_id": user.id, "status": "pending"})
        if not record:
            logger.warning(f"❌ No pending application found for {user.id} ({user.first_name})")
            await event.reply("❌ உங்கள் விண்ணப்பம் காணப்படவில்லை. முதலில் குழுவில் சேர விண்ணப்பிக்கவும்.")
            return

        try:
            logger.info(f"📥 Downloading voice note from {user.id}")
            voice_data = await event.download_media(bytes)
            logger.info(f"✅ Voice note downloaded for {user.id}")
        except Exception as e:
            logger.error(f"❌ Failed to download voice for {user.id}: {e}")
            await event.reply("❌ குரல் பதிவை பதிவிறக்க முடியவில்லை. மீண்டும் முயற்சிக்கவும்.")
            return

        if not is_valid_voice(voice_data):
            await event.reply("❌ குரல் பதிவு மிகக் குறுகியது அல்லது தெளிவற்றது. மீண்டும் அனுப்பவும்.")
            return

        try:
            logger.info(f"📤 Forwarding voice note from {user.id} to MODLOG_CHAT")
            msg = await event.forward_to(Config.MODLOG_CHAT)
            await event.reply("✅ குரல் பதிவு பெறப்பட்டது. நிர்வாகி விரைவில் பதிலளிப்பார்.")
            
            # Update database status and store message ID
            pending.update_one(
                {"user_id": user.id},
                {"$set": {"status": "voice_sent", "msg_id": msg.id}}
            )
            logger.info(f"💾 Updated database for {user.id} to 'voice_sent'")

            # Notify mod group with approve/reject buttons
            await bot.send_message(
                Config.MODLOG_CHAT,
                f"🎤 செல்லுபடியான குரல் பதிவு from [{esc(user.first_name)}](tg://user?id={user.id}) (`{user.id}`)",
                buttons=[
                    [Button.inline("✅ Approve", data=f"approve_{user.id}"),
                     Button.inline("❌ Reject", data=f"reject_{user.id}")]
                ],
                parse_mode='markdown'
            )
            logger.info(f"✅ Voice from {user.id} forwarded and buttons sent to mod group")
        except Exception as e:
            error_msg = f"❌ Failed to forward/process voice for {user.id}: {e}"
            logger.error(error_msg)
            await log_mod(error_msg)

    # Handle user joining the group (ChatAction)
    @bot.on(events.ChatAction)
    async def chat_action_handler(event):
        # Only proceed if it's our target group
        if event.chat_id != Config.GROUP_ID:
            return

        # Check for user joining (this is the standard event for users joining)
        if event.user_joined or event.user_added:
            users = event.users if event.users else [await event.get_user()]
            logger.info(f"👥 ChatAction event received for group {event.chat_id}")
            for user in users:
                if not user:
                    continue
                logger.info(f"📥 User joined: {user.id} ({user.first_name})")

                # Check if the user already has a pending or started record
                existing_record = pending.find_one({"user_id": user.id})
                if existing_record and existing_record.get("status") in ["pending", "started"]:
                    logger.info(f"🔁 User {user.id} already has a pending/started record. Updating.")
                    # Update the record to pending upon actual join
                    pending.update_one(
                        {"user_id": user.id},
                        {"$set": {
                            "request_time": datetime.now(timezone.utc),
                            "status": "pending" # Ensure status is pending
                        }}
                    )
                else:
                    # Create a new pending record if none exists or status is different
                    logger.info(f"🆕 Creating new pending record for user {user.id}")
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

                # Send welcome message and start reminder
                try:
                    logger.info(f"📤 Sending WELCOME_MSG to {user.id}")
                    await bot.send_message(user.id, WELCOME_MSG.format(name=esc(user.first_name)))
                    logger.info(f"✅ Sent welcome DM to {user.id}")
                    # Start reminder task
                    asyncio.create_task(reminder_task(user.id, user.first_name))
                except errors.UserIsBlockedError:
                    logger.warning(f"🚫 User {user.id} has blocked the bot. Cannot send welcome message.")
                    await log_mod(f"⚠️ DM failed for {user.id} ({user.first_name}): User blocked the bot.")
                except errors.InputUserDeactivatedError:
                    logger.warning(f"💀 User {user.id} account is deactivated.")
                    await log_mod(f"⚠️ DM failed for {user.id} ({user.first_name}): User account deactivated.")
                except Exception as e:
                    error_msg = f"❌ Failed to DM {user.id} ({user.first_name}): {type(e).__name__}: {e}"
                    logger.error(error_msg)
                    await log_mod(error_msg)
        # Optional: Handle join requests if needed (though ChatAction should cover standard joins)
        # elif isinstance(event.action_message.action, types.ChatActionRequestedJoin):
        #    # ... (similar logic as above) ...
        #    pass # Placeholder for explicit join request handling if needed

    # Approval/Rejection callback
    @bot.on(events.CallbackQuery(pattern=r"^(approve|reject)_(\d+)$"))
    async def approve_handler(event):
        if event.sender_id not in Config.ADMINS:
            await event.answer("🚫 உங்களுக்கு அனுமதி இல்லை.", alert=True)
            return

        action, user_id_str = event.data.decode().split("_")
        user_id = int(user_id_str)
        logger.info(f"🖱️ Admin {event.sender_id} clicked {action} for user {user_id}")
        try:
            user = await bot.get_entity(user_id)
        except Exception as e:
            logger.error(f"❌ Failed to get user {user_id}: {e}")
            await event.answer("❌ User not found", alert=True)
            return

        if action == "approve":
            try:
                logger.info(f"✅ Approving user {user.id}")
                # Grant view_messages permission (assuming default restrictions)
                await bot.edit_permissions(Config.GROUP_ID, user_id, view_messages=True)
                group_id_part = str(Config.GROUP_ID)[4:] # Remove -100 prefix for link
                await bot.send_message(
                    user_id,
                    APPROVED_MSG.format(
                        name=esc(user.first_name),
                        group_id_part=group_id_part,
                        topic_id=Config.TOPIC_ID
                    )
                )
                pending.update_one({"user_id": user_id}, {"$set": {"status": "approved"}})
                await event.edit(f"✅ Approved user {user.first_name} (`{user.id}`)")
                await log_mod(f"✅ Approved `{user.id}` — {esc(user.first_name)}")
                await event.answer("✅ Approved!", alert=True)
            except Exception as e:
                error_msg = f"❌ Approval failed for {user.id}: {e}"
                logger.error(error_msg)
                await event.edit(error_msg)
                await event.answer("❌ Approval failed", alert=True)
        else: # Reject
            try:
                logger.info(f"❌ Rejecting user {user.id}")
                await bot.send_message(user_id, REJECTED_MSG)
                pending.update_one({"user_id": user_id}, {"$set": {"status": "rejected"}})
                await event.edit(f"❌ Rejected user {user.first_name} (`{user.id}`)")
                await log_mod(f"❌ Rejected `{user.id}` — {esc(user.first_name)}")
                await event.answer("❌ Rejected!", alert=True)
            except Exception as e:
                error_msg = f"❌ Rejection failed for {user.id}: {e}"
                logger.error(error_msg)
                await event.edit(error_msg)
                await event.answer("❌ Rejection failed", alert=True)

    # Start command
    @bot.on(events.NewMessage(pattern='/start'))
    async def start(event):
        if event.is_private:
            logger.info(f"🚀 /start command received from {event.sender_id}")
            await event.reply(
                START_MSG,
                buttons=[[Button.url("🔗 குழுவில் சேரவும்", "https://t.me/+_1n657JUXHIzODk1")]]
            )
        # Delete the /start message in group chats (if accidentally sent there)
        if not event.is_private:
             await event.delete()

    # Handle "Hi", "Join", etc. (Initial interaction)
    @bot.on(events.NewMessage(func=lambda e: e.is_private and e.text and e.text.lower().strip() in ['hi', 'hello', 'join', 'start']))
    async def greet(event):
        user = await event.get_sender()
        if not user:
             return
        logger.info(f"💬 Greeting trigger received from {user.id}: '{event.text}'")

        # Create or update a 'started' record to track initial contact
        pending.update_one(
            {"user_id": user.id},
            {"$set": {
                "first_name": user.first_name,
                "username": user.username,
                "last_interaction": datetime.now(timezone.utc),
                "status": "started" # Indicate they've started the process
            }},
            upsert=True
        )
        logger.info(f"💾 Updated/created 'started' record for {user.id}")

        await event.reply(
            "✅ நீங்கள் தயாராக உள்ளீர்கள்!\n\n"
            "இப்போது குழுவில் சேர விண்ணப்பிக்கவும்:\n"
            "https://t.me/+_1n657JUXHIzODk1  \n\n"
            "பின்னர் ஒரு **குரல் பதிவு** அனுப்பவும்.",
            buttons=[[Button.url("🔗 குழுவில் சேரவும்", "https://t.me/+_1n657JUXHIzODk1")]]
        )

    # Reminder task
    async def reminder_task(user_id, name):
        logger.info(f"⏱️ Starting reminder task for user {user_id}")
        await asyncio.sleep(Config.TIMEOUT)
        # Check if the user is still pending
        record = pending.find_one({"user_id": user_id, "status": "pending"})
        if record:
            try:
                logger.info(f"⏰ Sending reminder to user {user_id}")
                await bot.send_message(user_id, REMINDER_MSG.format(name=esc(name)))
                logger.info(f"✅ Reminder sent to {user_id}")
            except errors.UserIsBlockedError:
                logger.warning(f"🚫 Reminder failed for {user_id}: User blocked the bot.")
                await log_mod(f"⚠️ Reminder failed for {user_id} ({name}): User blocked the bot.")
            except errors.InputUserDeactivatedError:
                 logger.warning(f"💀 Reminder failed for {user_id}: User account deactivated.")
                 await log_mod(f"⚠️ Reminder failed for {user_id} ({name}): User account deactivated.")
            except Exception as e:
                logger.warning(f"⚠️ Failed to send reminder to {user_id}: {e}")
        else:
            logger.info(f"ℹ️ Reminder task for {user_id} cancelled (status not pending).")

    logger.info("✅ All handlers registered. Bot is live and waiting for events.")
    await bot.run_until_disconnected()

# ---------------- Start ----------------
if __name__ == '__main__':
    # nest_asyncio is generally not needed if running the script directly
    # import nest_asyncio
    # nest_asyncio.apply()
    try:
        loop = asyncio.get_event_loop()
        loop.run_until_complete(start_bot())
    except KeyboardInterrupt:
        logger.info("🛑 Bot stopped by user.")
    except Exception as e:
        logger.critical(f"💥 Fatal error occurred: {e}", exc_info=True)