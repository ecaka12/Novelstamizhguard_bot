# config.py
import os
from typing import List

class Config:
    API_ID = int(os.getenv("API_ID"))
    API_HASH = os.getenv("API_HASH")
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    
    GROUP_ID = int(os.getenv("GROUP_ID"))
    MODLOG_GROUP_ID = int(os.getenv("MODLOG_GROUP_ID"))
    
    # Ensure ADMINS is a comma-separated list of IDs in your Railway env vars
    ADMINS = list(map(int, os.getenv("ADMINS", "5504106603").split(',')))
    
    MONGO_URI = os.getenv("MONGO_URI")
    
    # Optional: Topic ID if using forum topics
    TOPIC_ID = int(os.getenv("TOPIC_ID", "0"))
    
    # Updated timeout to match your 2-hour messages
    VOICE_PENDING_TIMEOUT = 2 * 60 * 60  # 2 hours (7200 seconds)