from app import create_app, socketio
import os
from dotenv import load_dotenv
import sys

# Load biến môi trường
load_dotenv()

# Tạo app Flask
app = create_app()

# Cố gắng import hàm seed_database từ file seed_data.py
# Để tránh lỗi nếu bạn lỡ xóa file seed_data.py sau này
try:
    from seed_data import seed_database
    HAS_SEED_SCRIPT = True
except ImportError:
    HAS_SEED_SCRIPT = False

if __name__ == '__main__':
    print("----------------------------------------------------------------")
    
    # --- ĐOẠN CODE AUTO SEED ---
    if HAS_SEED_SCRIPT:
        print("🌱 Đang tự động seed dữ liệu mẫu (Auto-seeding)...")
        try:
            # Gọi hàm seed_database() từ file seed_data.py
            # Hàm này sẽ xóa DB cũ và tạo lại dữ liệu mới (bao gồm chat logs > 300 dòng)
            seed_database()
            print("✅ Seed dữ liệu thành công!")
        except Exception as e:
            print(f"⚠️  Lỗi khi seed dữ liệu: {e}")
            print("   -> Server vẫn sẽ tiếp tục chạy với dữ liệu cũ (nếu có).")
    else:
        print("⚠️  Không tìm thấy file seed_data.py, bỏ qua bước seed dữ liệu.")
    
    print("----------------------------------------------------------------")
    print("🚀 Server is running! Click the link below to open:")
    print("http://127.0.0.1:5000")
    print("----------------------------------------------------------------")
    
    # Sử dụng socketio.run thay vì app.run
    socketio.run(app, host='0.0.0.0', port=5000, debug=True, allow_unsafe_werkzeug=True)