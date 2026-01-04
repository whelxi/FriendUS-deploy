FriendUS
FriendUS is a multi-functional web application designed to be your all-in-one companion. It integrates real-time chat, financial tracking, event planning, weather updates, and map services into a single cohesive platform.

🔗 Live Demo: https://friendus.onrender.com/

🚀 Features
Real-time Chat: Instant messaging with online/offline status tracking using WebSockets.

Finance Manager: Track group funds and personal expenses.

Event Planner: Organize schedules and plans.

Interactive Map: Location services and mapping features.

Weather: Real-time weather updates.

Secure Authentication: User login system integrated with Google OAuth.

🛠 Tech Stack
Backend: Python 3.9+, Flask

Real-time Engine: Flask-SocketIO (Asynchronous mode with Eventlet)

Database: SQLAlchemy (SQLite for Dev, PostgreSQL for Prod)

Frontend: Bootstrap-Flask, Jinja2

Deployment: Docker, Render (Infrastructure as Code)

⚙️ Local Installation
Follow these steps to run the application on your local machine.

1. Clone the Repository
Bash

git clone https://github.com/your-username/computional-thinking-4gotten.git
cd computional-thinking-4gotten
2. Set up a Virtual Environment
It is recommended to use a virtual environment to manage dependencies.

Bash

# Windows
python -m venv venv
venv\Scripts\activate

# macOS/Linux
python3 -m venv venv
source venv/bin/activate
3. Install Dependencies
Bash

pip install -r requirements.txt
Note: Ensure you have eventlet installed as it is required for the async socket server.

4. Configure Environment Variables
Create a .env file in the root directory. You can use the following template based on config.py:

Đoạn mã

# App Security
SECRET_KEY=your_super_secret_key

# Database (Default is SQLite if left empty)
DATABASE_URL=sqlite:///friendus.db

# Google OAuth (Required for Login)
GOOGLE_CLIENT_ID=your_google_client_id
GOOGLE_CLIENT_SECRET=your_google_client_secret

# Optional: Timezone
TZ=Asia/Ho_Chi_Minh
5. Run the Application
The application uses socketio.run to start the server.

Bash

python run.py
Access the app at: http://127.0.0.1:5000

☁️ Deployment on Render
This project is configured for seamless deployment on Render using a render.yaml Blueprint and Docker.

Deployment Steps
Push to GitHub: Ensure your latest code (including render.yaml and Dockerfile) is on GitHub.

Create a Render Account: Go to dashboard.render.com.

New Blueprint: Click New + and select Blueprint.

Connect Repository: Connect your GitHub account and select the FriendUS repository.

Auto-Configuration: Render will detect the render.yaml file and automatically configure the service as a Docker environment.

Apply: Click Apply to start the build.

Production Configuration
To ensure the app runs correctly in production, you must set the following Environment Variables in the Render Dashboard (do not commit these to GitHub):

SECRET_KEY: A strong random string.

DATABASE_URL: Your PostgreSQL connection string (Render usually provides this if you add a Database service).

GOOGLE_CLIENT_ID & GOOGLE_CLIENT_SECRET: From your Google Cloud Console.

FLASK_ENV: Set to production.

TZ: Set to your local timezone (e.g., Asia/Ho_Chi_Minh) to fix server time discrepancies.

Deployment Notes
SocketIO: The app is configured with cors_allowed_origins="*" and uses eventlet to handle WebSocket connections efficiently on Render.

ProxyFix: The app uses Werkzeug ProxyFix to correctly handle HTTPS headers behind Render's load balancer.

Database: The pool_pre_ping option is enabled to prevent "SSL connection closed" errors common in cloud databases.

Developed for Computational Thinking - Group 4gotten