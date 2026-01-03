# Sử dụng Python 3.11 để khớp với render.yaml của bạn
FROM python:3.11-slim

# Thiết lập các biến môi trường để Python chạy ổn định trong Docker
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PORT=10000

# Cài đặt thư viện hệ thống cần thiết (giảm thiểu để nhẹ image)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# --- BƯỚC QUAN TRỌNG NHẤT ĐỂ BUILD NHANH ---
# Chỉ copy requirements trước. Nếu file này không đổi, Render sẽ dùng Cache.
COPY requirements.txt .

# Cài đặt thư viện (Sử dụng --no-cache-dir để image gọn nhẹ)
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# --- COPY TOÀN BỘ CODE VÀO SAU ---
COPY . .

# Mở cổng 10000
EXPOSE 10000

# Lệnh khởi chạy tối ưu cho SocketIO + Gunicorn
# Sử dụng gevent để hỗ trợ kết nối đồng thời tốt hơn
CMD ["gunicorn", "-k", "gevent", "-w", "1", "--threads", "4", "--bind", "0.0.0.0:10000", "run:app"]