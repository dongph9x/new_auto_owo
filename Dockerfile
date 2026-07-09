FROM python:3.11-slim

# git: needed to install the pinned discord.py-self commit
# libgomp1: runtime dependency of onnxruntime (OpenMP)
RUN apt-get update && apt-get install -y --no-install-recommends \
        git libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Python deps = requirements.txt + the heavy libs that neura_setup.py adds
# (numpy / pillow / onnxruntime for the offline captcha solver).
RUN pip install --no-cache-dir \
        "discord.py-self @ git+https://github.com/dolfies/discord.py-self@20ae80b398ec83fa272f0a96812140e14868c88" \
        Flask==2.3.0 \
        requests==2.31.0 \
        aiohttp==3.12.15 \
        rich==14.2.0 \
        plyer==2.1.0 \
        playsound3==3.3.0 \
        python-dotenv==1.2.1 \
        cryptography \
        numpy \
        pillow \
        onnxruntime

# App code. config/ and data/ are bind-mounted at runtime (see docker-compose.yml)
COPY . .

ENV NEURA_AUTOSTART=1 \
    NEURA_SKIP_DEP_CHECK=1 \
    PYTHONUNBUFFERED=1

EXPOSE 8000

CMD ["python", "neura.py"]
