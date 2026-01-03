from app import create_app, socketio
import os
from dotenv import load_dotenv
import sys

# Load biến môi trường
load_dotenv()

# Tạo app Flask
app = create_app()

# ----------------------------------------------------------------
# CẤU HÌNH AUTO-SEED (Quan trọng: Để ở ngoài để Gunicorn chạy được)
# ----------------------------------------------------------------
try:
    from seed_data import seed_database
    HAS_SEED_SCRIPT = True
except ImportError:
    HAS_SEED_SCRIPT = False

# Kiểm tra logic seed
# Mặc định ENABLE_SEED là 'True'. Nếu muốn tắt trên Render, bạn vào Environment Variables đặt là 'False'.
if HAS_SEED_SCRIPT:
    # Chỉ in log ngăn cách nếu thực sự chạy seed
    if os.environ.get('ENABLE_SEED', 'True') == 'True':
        print("----------------------------------------------------------------")
        print("🌱 [Auto-Seeding] Đang khởi tạo dữ liệu mẫu...")
        try:
            seed_database()
            print("✅ [Auto-Seeding] Thành công!")
        except Exception as e:
            print(f"⚠️ [Auto-Seeding] Lỗi: {e}")
        print("----------------------------------------------------------------")
    else:
        print("⏭️ [Auto-Seeding] Bỏ qua (ENABLE_SEED=False)")

# ----------------------------------------------------------------
# CẤU HÌNH CHẠY LOCAL (Khi bạn chạy: python run.py)
# ----------------------------------------------------------------
if __name__ == '__main__':
    print("----------------------------------------------------------------")
    
    # Lấy PORT từ biến môi trường (Render cấp), mặc định 5000 nếu chạy local
    port = int(os.environ.get("PORT", 5000))
    
    print(f"🚀 Server is starting on port {port}...")
    print("----------------------------------------------------------------")
    
    # Start app với SocketIO
    # Lưu ý: allow_unsafe_werkzeug=True hữu ích khi chạy dev nhưng cẩn thận trên prod
    socketio.run(app, host='0.0.0.0', port=port, debug=False, allow_unsafe_werkzeug=True)