FROM python:3.10

WORKDIR /usr/src/

RUN apt install git

#RUN git clone https://github.com/impossible-bosses/ibce-bots

COPY . /usr/src/ibce-bots/

WORKDIR /usr/src/ibce-bots/

RUN apt-get update && apt-get install -y \
    wget \
    curl \
    gnupg \
    ca-certificates \
    libnss3 \
    libnspr4 \
    libx11-xcb1 \
    libxcomposite1 \
    libxdamage1 \
    libxrandr2 \
    libxss1 \
    libasound2 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libgtk-3-0 \
    libgtk-4-1 \
    libcups2 \
    libxkbcommon0 \
    libxshmfence1 \
    libgbm1 \
    libdrm2 \
    libxext6 \
    libxfixes3 \
    libxinerama1 \
    libxcursor1 \
    libgl1 \
    libx11-6 \
    libxrender1 \
    libgstreamer1.0-0 \
    libgstreamer-plugins-base1.0-0 \
    libgstreamer-plugins-good1.0-0 \
    libgstreamer-plugins-bad1.0-0 \
    libgstreamer-plugins-ugly1.0-0 \
    gstreamer1.0-libav \
    gstreamer1.0-gl \
    gstreamer1.0-gtk3 \
    gstreamer1.0-pulseaudio \
    libopus0 \
    libvpx7 \
    libwoff1 \
    libwoff2-1 \
    libwoff2dec0 \
    libflite1 \
    libenchant-2-2 \
    libsecret-1-0 \
    libgraphene-1.0-0 \
    libavif15 \
    libharfbuzz-icu0 \
    libhyphen0 \
    libmanette-0.2-0 \
    libgles2 \
    libx264-160 \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

RUN pip install --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt && playwright install-deps && playwright install

COPY constants.py ./

CMD [ "python", "./main.py" ]
