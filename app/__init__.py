import os
import time
from flask import Flask
from config import Config
from app.extensions import db, login_manager, bootstrap, socketio, oauth
from app.events import register_socketio_events
# [MỚI 1] Import ProxyFix để fix lỗi form không hoạt động trên Render
from werkzeug.middleware.proxy_fix import ProxyFix 

def create_app(config_class=Config):
    # --- [CẬP NHẬT] FIX TIMEZONE TRÊN RENDER ---
    # Render chạy trên Linux, cần set lại giờ hệ thống của Python theo biến TZ
    tz = os.environ.get('TZ')
    if tz:
        os.environ['TZ'] = tz
        time.tzset()  # Lệnh này bắt buộc Python cập nhật lại múi giờ
    # -------------------------------------------

    app = Flask(__name__)
    app.config.from_object(config_class)

    # [MỚI 2] Cấu hình ProxyFix
    # Dòng này cực quan trọng để Flask nhận diện đúng HTTPS trên Render
    # Nếu thiếu dòng này: Form Tags sẽ không lưu được, Link chuyển hướng bị lỗi http/https
    app.wsgi_app = ProxyFix(
        app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1
    )

    # Initialize Extensions
    db.init_app(app)
    login_manager.init_app(app)
    bootstrap.init_app(app)
    
    # [MỚI 3] Cập nhật init SocketIO
    # cors_allowed_origins="*": Cho phép kết nối từ mọi nguồn (tránh lỗi 400 Bad Request trên Render)
    # async_mode='eventlet': Chỉ định rõ worker (khớp với file requirements.txt của bạn)
    socketio.init_app(app, cors_allowed_origins="*", async_mode="threading")
    
    oauth.init_app(app)

    # Register Google Provider
    CONF_URL = 'https://accounts.google.com/.well-known/openid-configuration'
    oauth.register(
        name='google',
        server_metadata_url=CONF_URL,
        api_base_url='https://www.googleapis.com/oauth2/v3/',
        client_id=app.config.get('GOOGLE_CLIENT_ID'),
        client_secret=app.config.get('GOOGLE_CLIENT_SECRET'),
        client_kwargs={
            'scope': 'openid email profile'
        }
    )

    # Register Blueprints
    from app.blueprints.main import main_bp
    from app.blueprints.auth import auth_bp
    from app.blueprints.map import map_bp
    from app.blueprints.chat import chat_bp
    from app.blueprints.planner import planner_bp
    from app.blueprints.finance import finance_bp
    from app.blueprints.weather import weather_bp 

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp, url_prefix='/auth') 
    app.register_blueprint(map_bp)
    app.register_blueprint(chat_bp)
    app.register_blueprint(planner_bp)
    app.register_blueprint(finance_bp)
    app.register_blueprint(weather_bp, url_prefix='/weather')

    # Register Socket Events
    register_socketio_events(socketio)

    # Define User Loader
    from app.models import User, Room
    @login_manager.user_loader
    def load_user(user_id):
        # [MỚI 4] Thêm xử lý lỗi nếu user không tồn tại (tránh crash)
        if user_id is not None:
            return User.query.get(int(user_id))
        return None

    # Create DB and Populate if empty
    with app.app_context():
        db.create_all()

    return app