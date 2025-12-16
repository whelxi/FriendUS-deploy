import eventlet
eventlet.monkey_patch()

from app import create_app, socketio
from dotenv import load_dotenv
import os

load_dotenv()

app = create_app()

if __name__ == '__main__':
    socketio.run(
        app,
        host='0.0.0.0',
        port=int(os.environ.get('PORT', 5000)),
        debug=True
    )
