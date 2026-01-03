from app import create_app, socketio
import os
from dotenv import load_dotenv
import sys

# Load biến môi trường
load_dotenv()

# Tạo app Flask
app = create_app()

# --- SETUP DATABASE SEEDING ---
try:
    from seed_data import seed_database
    HAS_SEED_SCRIPT = True
except ImportError:
    HAS_SEED_SCRIPT = False

if __name__ == '__main__':
    print("----------------------------------------------------------------")
    
    # --- ĐOẠN CODE AUTO SEED ---
    # Lưu ý: Trên Render, nếu bạn dùng SQLite, dữ liệu sẽ mất sau mỗi lần Deploy
    # nên việc auto-seed này là CẦN THIẾT nếu bạn muốn có dữ liệu mẫu ngay.
    if HAS_SEED_SCRIPT:
        print("🌱 Đang tự động seed dữ liệu mẫu (Auto-seeding)...")
        try:
            # Bạn có thể thêm biến môi trường ENABLE_SEED=False trên Render nếu muốn tắt nó
            if os.environ.get('ENABLE_SEED', 'True') == 'True':
                seed_database()
                print("✅ Seed dữ liệu thành công!")
            else:
                print("⏭️  Bỏ qua seed do cấu hình ENABLE_SEED=False")
        except Exception as e:
            print(f"⚠️  Lỗi khi seed dữ liệu: {e}")
    else:
        print("⚠️  Không tìm thấy file seed_data.py, bỏ qua bước seed dữ liệu.")
    
    print("----------------------------------------------------------------")
    
    # --- QUAN TRỌNG: CẤU HÌNH PORT CHO RENDER ---
    # Lấy PORT từ biến môi trường Render, nếu không có (chạy local) thì lấy 5000
    port = int(os.environ.get("PORT", 5000))
    
    print(f"🚀 Server is running on port {port}!")
    print("----------------------------------------------------------------")
    
    # Start app
    socketio.run(app, host='0.0.0.0', port=port, debug=False, allow_unsafe_werkzeug=True)