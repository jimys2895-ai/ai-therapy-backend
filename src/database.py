from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import MongoClient
from .config import settings
import asyncio

class Database:
    client: AsyncIOMotorClient = None
    database = None

db = Database()

# MongoDB connection
async def connect_to_mongo():
    """Create database connection"""
    db.client = AsyncIOMotorClient(settings.DATABASE_URL)
    db.database = db.client.ai_therapy
    print("Connected to MongoDB")

async def close_mongo_connection():
    """Close database connection"""
    if db.client:
        db.client.close()
        print("Disconnected from MongoDB")

def get_database():
    """Get database instance"""
    return db.database

# Collections
def get_users_collection():
    return db.database.users

def get_subscriptions_collection():
    return db.database.subscriptions

def get_patients_collection():
    return db.database.patients

def get_sessions_collection():
    return db.database.sessions

def get_settings_collection():
    return db.database.user_settings

def get_voice_messages_collection():
    return db.database.voice_messages

def get_recordings_collection():
    return db.database.recordings
