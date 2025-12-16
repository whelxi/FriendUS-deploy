import os
# 1. ADD THIS IMPORT
from dotenv import load_dotenv 

# 2. LOAD THE .ENV FILE
# This tells Python to look for a file named ".env" in the same directory
basedir = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(basedir, '.env'))

class Config:
    # Base Directory
    BASEDIR = basedir

    # Security
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-change-me'

    # Database
    database_url = os.environ.get('DATABASE_URL')
    if database_url and database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)

    SQLALCHEMY_DATABASE_URI = database_url or 'sqlite:///' + os.path.join(BASEDIR, 'friendus.db')

    # Google Authentication
    GOOGLE_CLIENT_ID = os.environ.get('GOOGLE_CLIENT_ID')
    GOOGLE_CLIENT_SECRET = os.environ.get('GOOGLE_CLIENT_SECRET')

    # --- VIETMAP KEYS ---
    # Now these will actually load from your .env file!
    VIETMAP_TILE_KEY = os.environ.get('VIETMAP_TILE_KEY')
    VIETMAP_SERVICE_KEY = os.environ.get('VIETMAP_SERVICE_KEY')

    #Gemini
    GOOGLE_API_KEY = os.environ.get('GOOGLE_API_KEY')
