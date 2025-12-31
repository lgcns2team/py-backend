# Python 3.11 slim 이미지 사용
FROM python:3.11-slim

# 환경 변수 설정
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# 작업 디렉토리 설정
WORKDIR /app

# 시스템 의존성 설치 (PostgreSQL 클라이언트 라이브러리 필요)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Python 의존성 설치
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 애플리케이션 코드 복사
COPY . .

# 포트 노출
EXPOSE 8000

# 서버 실행 (uvicorn ASGI 서버 사용)
CMD ["uvicorn", "config.asgi:application", "--host", "0.0.0.0", "--port", "8000"]
