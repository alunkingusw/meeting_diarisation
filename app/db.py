import os
from pymongo import MongoClient
from app.startup import MONGO_URL, MONGO_DB

client = MongoClient(MONGO_URL)
db = client[MONGO_DB]
