# config.py
import os

class Config:
    API_ID = int(os.getenv("API_ID"))
    API_HASH = os.getenv("API_HASH")
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    MONGO_URI = os.getenv("MONGO_URI")
    GROUP_ID = int(os.getenv("GROUP_ID"))
    TOPIC_ID = int(os.getenv("TOPIC_ID", 0))  # Optional
    MODLOG_CHAT = int(os.getenv("MODLOG_CHAT"))
    ADMINS = [int(id) for id in os.getenv("ADMINS", "").split(",") if id.strip()]
    TIMEOUT = int(os.getenv("TIMEOUT", "7200"))  # 2 hours