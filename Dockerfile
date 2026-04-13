# =============================================================
# Dockerfile — Mission Agent v2
# =============================================================
FROM python:3.11-slim

WORKDIR /app

# Dépendances système
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Dépendances Python (séparées pour profiter du cache Docker layer)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Code source (hors tests et fichiers dev)
COPY agents/     ./agents/
COPY core/       ./core/
COPY config/     ./config/
COPY sources/    ./sources/
COPY main.py     .

# Dossier de données persistant
RUN mkdir -p /app/data

# Variables d'environnement — toutes surchargeables via Railway Variables
ENV DB_PATH=/app/data/missions.db
ENV TELEGRAM_TOKEN=""
ENV TELEGRAM_CHAT_ID=""
ENV OPENAI_API_KEY=""
ENV ACTIVE_PROFILE="all"
ENV TELEGRAM_BOT_ENABLED="true"
ENV SEMANTIC_SCORING="true"
ENV IDEAL_PROFILE_TEXT=""
ENV TWITTER_BEARER_TOKEN=""
ENV GITHUB_TOKEN=""
ENV LOOP_INTERVAL="300"
ENV REQUEST_DELAY="2"

# Healthcheck : vérifie que Python et la DB sont OK
HEALTHCHECK --interval=60s --timeout=10s --start-period=30s --retries=3 \
    CMD python -c "import sqlite3, os; sqlite3.connect(os.environ.get('DB_PATH','data/missions.db')).close(); print('OK')"

CMD ["python", "main.py", "loop"]
