import os
import secrets  # [QUAN TRỌNG] Thêm thư viện này để tạo khóa bảo mật
from dotenv import load_dotenv 

# 2. LOAD THE .ENV FILE
basedir = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(basedir, '.env'))

class Config:
    # Base Directory
    BASEDIR = basedir

    # Security - [ĐÃ SỬA]
    # Dùng secrets.token_hex(32) để mỗi lần server Render khởi động lại,
    # nó sẽ tạo một chìa khóa mới. Điều này giúp vô hiệu hóa toàn bộ cookie cũ,
    # ngăn chặn triệt để việc đăng nhập nhầm vào tài khoản người khác.
    SECRET_KEY = os.environ.get('SECRET_KEY') or secrets.token_hex(32)

    # Database - [ĐÚNG RỒI]
    database_url = os.environ.get('DATABASE_URL')
    if database_url and database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)

    SQLALCHEMY_DATABASE_URI = database_url or 'sqlite:///' + os.path.join(BASEDIR, 'friendus.db')

    # Google Authentication
    GOOGLE_CLIENT_ID = os.environ.get('GOOGLE_CLIENT_ID')
    GOOGLE_CLIENT_SECRET = os.environ.get('GOOGLE_CLIENT_SECRET')

    # --- VIETMAP KEYS ---
    VIETMAP_TILE_KEY = os.environ.get('VIETMAP_TILE_KEY')
    VIETMAP_SERVICE_KEY = os.environ.get('VIETMAP_SERVICE_KEY')

    # Gemini
    GOOGLE_API_KEY = os.environ.get('GOOGLE_API_KEY')