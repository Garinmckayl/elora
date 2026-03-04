FROM python:3.11-slim

# System deps for httpx/SSL and playwright
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 libcups2 \
    libdrm2 libdbus-1-3 libxkbcommon0 libxcomposite1 libxdamage1 \
    libxfixes3 libxrandr2 libgbm1 libasound2 libpango-1.0-0 \
    libcairo2 libatspi2.0-0 libx11-6 libxext6 libxcb1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install all dependencies (agent + adk + main app)
COPY requirements.txt requirements-agent.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright for browser_worker tool
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
RUN pip install --no-cache-dir playwright && playwright install chromium

# Copy all source
COPY . .

# FastAPI server
CMD ["python", "main.py"]
