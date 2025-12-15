from flask import Flask
from config import Config
from app.extensions import db, login_manager, bootstrap, socketio, oauth
from app.events import register_socketio_events

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Initialize Extensions
    db.init_app(app)
    login_manager.init_app(app)
    bootstrap.init_app(app)
    socketio.init_app(app)
    oauth.init_app(app)

    # Register Google Provider
    CONF_URL = 'https://accounts.google.com/.well-known/openid-configuration'
    oauth.register(
        name='google',
        server_metadata_url=CONF_URL,
        # --- ADDED THIS LINE ---
        api_base_url='https://www.googleapis.com/oauth2/v3/',
        # -----------------------
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

    app.register_blueprint(main_bp)
    
    # --- THIS IS THE CRITICAL FIX ---
    app.register_blueprint(auth_bp, url_prefix='/auth') 
    # --------------------------------
    
    app.register_blueprint(map_bp)
    app.register_blueprint(chat_bp)
    app.register_blueprint(planner_bp)
    app.register_blueprint(finance_bp)

    # Register Socket Events
    register_socketio_events(socketio)

    # Define User Loader
    from app.models import User, Room
    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    # Create DB and Populate if empty
    with app.app_context():
        db.create_all()
        if not Room.query.filter_by(name='general').first():
            general_room = Room(name='general', description='A general chat room for all users.')
            db.session.add(general_room)
            db.session.commit()
            print("Created 'general' room.")

    return app