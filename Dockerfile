# Sử dụng Python 3.11 bản slim để nhẹ nhất có thể (dưới 100MB gốc)
FROM python:3.9-slim

# Thiết lập biến môi trường để log hiện ra ngay lập tức và không tạo file .pyc rác
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Thiết lập thư mục làm việc
WORKDIR /app

# [QUAN TRỌNG] Cài đặt các gói hệ thống cần thiết (nếu có)
# autoremove để dọn dẹp ngay sau khi cài giúp giảm dung lượng ảnh
RUN apt-get update && apt-get install -y \
    gcc \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# [CHIẾN THUẬT CACHE] Copy file requirements trước
# Nếu file này không đổi, Docker sẽ bỏ qua bước RUN pip install bên dưới
COPY requirements.txt .

# Cài đặt thư viện:
# 1. Cài PyTorch bản CPU-only (giảm dung lượng từ 2GB -> 200MB)
# 2. Cài các thư viện còn lại từ requirements.txt
RUN pip install --no-cache-dir torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu && \
    pip install --no-cache-dir -r requirements.txt && \
    pip install eventlet==0.33.3 
    # Cài thêm eventlet như đã bàn ở câu trước

# Copy toàn bộ code vào
COPY . .

# Mở port 10000 (khớp với render.yaml)
EXPOSE 10000

# Lệnh chạy server với Gunicorn và Eventlet
CMD ["gunicorn", "--worker-class", "eventlet", "-w", "1", "--bind", "0.0.0.0:10000", "run:app"]