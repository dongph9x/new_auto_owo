FROM python:3.11-slim

WORKDIR /app

COPY control_bot/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Only needs bot.py + read-only access to config/accounts.json (for the
# account-name autocomplete) — mounted via docker-compose, not copied in.
COPY control_bot/bot.py .

ENV PYTHONUNBUFFERED=1

CMD ["python", "bot.py"]
