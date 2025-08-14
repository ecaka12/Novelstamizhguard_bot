import os
from typing import List

class Config:
    API_ID = int(os.getenv("API_ID"))
    API_HASH = os.getenv("API_HASH")
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    
    GROUP_ID = int(os.getenv("GROUP_ID"))
    MODLOG_GROUP_ID = int(os.getenv("MODLOG_GROUP_ID"))
    
    ADMINS = list(map(int, os.getenv("ADMINS", "5504106603").split(',')))
    
    MONGO_URI = os.getenv("MONGO_URI")
    
    TOPIC_ID = int(os.getenv("TOPIC_ID", "0"))
    
    VOICE_PENDING_TIMEOUT = 24 * 60 * 60  # 24 hours