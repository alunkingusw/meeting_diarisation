import os
from pymongo import MongoClient

MONGO_URL = os.getenv("MONGO_URL", "mongodb://localhost:27017")
MONGO_DB = os.getenv("MONGO_DB", "diarisation_db")

client = MongoClient(MONGO_URL)
db = client[MONGO_DB]
