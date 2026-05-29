import asyncio
import sys
import os

# Add the src directory to the Python path
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from src.database import connect_to_mongo, close_mongo_connection, get_plans_collection
from src.models.plans import DEFAULT_PLANS

async def init_database():
    """Initialize the database with default data"""
    print("Connecting to MongoDB...")
    await connect_to_mongo()
    
    print("Initializing default subscription plans...")
    plans_collection = get_plans_collection()
    
    for plan_data in DEFAULT_PLANS:
        existing_plan = await plans_collection.find_one({"name": plan_data["name"]})
        if not existing_plan:
            await plans_collection.insert_one(plan_data)
            print(f"✓ Created plan: {plan_data['display_name']}")
        else:
            print(f"✓ Plan already exists: {plan_data['display_name']}")
    
    # Create indexes for better performance
    print("Creating database indexes...")
    
    # Users collection indexes
    users_collection = get_plans_collection().database.users
    await users_collection.create_index("email", unique=True)
    await users_collection.create_index("subscription_plan")
    await users_collection.create_index("user_type")
    await users_collection.create_index("is_active")
    print("✓ Created users collection indexes")
    
    # Plans collection indexes
    await plans_collection.create_index("name", unique=True)
    await plans_collection.create_index("is_active")
    print("✓ Created plans collection indexes")
    
    # Subscriptions collection indexes
    subscriptions_collection = get_plans_collection().database.subscriptions
    await subscriptions_collection.create_index("user_id")
    await subscriptions_collection.create_index("plan_id")
    await subscriptions_collection.create_index("status")
    print("✓ Created subscriptions collection indexes")
    
    print("\n🎉 Database initialization completed successfully!")
    
    await close_mongo_connection()

if __name__ == "__main__":
    asyncio.run(init_database())
