
from pymongo import MongoClient

client = MongoClient(
    "mongodb://localhost:27017/",
    serverSelectionTimeoutMS=5000
)

try:
    client.admin.command("ping")
    print("MongoDB connected successfully!")

    db = client["ai_health_db"]
    patients = db["patients"]

    print("Database: ai_health_db")
    print("Collection: patients")

except Exception as e:
    print("MongoDB connection failed:", e)

finally:
    client.close()
