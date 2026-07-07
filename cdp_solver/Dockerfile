# Heavy on purpose: needs a real Chrome + virtual display (Xvfb), which the main
# neuraself image intentionally doesn't carry. Based on SeleniumBase's own
# reference Dockerfile (github.com/seleniumbase/SeleniumBase/blob/master/Dockerfile),
# since guessing the Chrome/Xvfb/font setup tends to fail in non-obvious ways.
FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive \
    DISPLAY=:99 \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
        wget curl gnupg unzip sudo \
        xvfb x11-utils \
        fonts-liberation fonts-noto-color-emoji \
        libnss3 libxi6 libgconf-2-4 \
        python3 python3-pip python3-venv \
    && rm -rf /var/lib/apt/lists/*

# Google Chrome (stable), same approach SeleniumBase's own Dockerfile uses.
RUN wget -q https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb \
    && apt-get update \
    && apt-get install -y --no-install-recommends ./google-chrome-stable_current_amd64.deb \
    && rm google-chrome-stable_current_amd64.deb \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY cdp_solver/requirements.txt .
RUN pip3 install --no-cache-dir --break-system-packages -r requirements.txt \
    && seleniumbase install chromedriver

COPY cdp_solver/service.py .

EXPOSE 8100

# Start the virtual display, then the Flask service.
COPY cdp_solver/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

CMD ["/entrypoint.sh"]
