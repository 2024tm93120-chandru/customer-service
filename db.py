import os
import sys
from pymongo import MongoClient
from flask import g

client = None

def get_db_client():
    """
    Initializes and returns a global MongoDB client.
    """
    global client
    if client is None:
        try:
            # Get URI from env, default to localhost
            uri = os.environ.get('MONGO_URI', 'mongodb://localhost:27017/')
            client = MongoClient(uri)
            # Ping the server to test the connection
            client.admin.command('ping')
            print("MongoDB connection successful.")
        except Exception as e:
            print(f"Failed to connect to MongoDB: {e}", file=sys.stderr)
            sys.exit(1) # Exit if DB connection fails
    return client

def get_db():
    """
    Gets the db instance (database) for the current request.
    Stores it in the Flask 'g' (global) context.
    """
    if 'db' not in g:
        db_name = os.environ.get('DB_NAME', 'customer_db')
        g.db = get_db_client()[db_name]
    return g.db

def close_db(e=None):
    """
    MongoDB client handles pooling. We don't need to
    close the connection on a per-request basis.
    This function is here to fit the Flask app context pattern.
    """
    pass