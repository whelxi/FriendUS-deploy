# Sử dụng bản Python gọn nhẹ để tiết kiệm dung lượng
FROM python:3.10-slim

# Cài đặt các thư viện hệ thống cần thiết (cho gevent và các thư viện C)
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Thiết lập thư mục làm việc
WORKDIR /app

# --- TỐI ƯU CACHE: Copy requirements trước ---
COPY requirements.txt .

# Cài đặt thư viện (Chỉ chạy lại nếu bạn sửa file requirements.txt)
# Dùng --no-cache-dir để giảm dung lượng image
RUN pip install --no-cache-dir -r requirements.txt

# --- Copy toàn bộ mã nguồn vào sau ---
COPY . .

# Mở cổng 10000 (Cổng mặc định của Render)
EXPOSE 10000

# Lệnh khởi chạy (Dùng gevent như đã thảo luận)
CMD ["gunicorn", "-k", "gevent", "-w", "1", "--bind", "0.0.0.0:10000", "run:app"]