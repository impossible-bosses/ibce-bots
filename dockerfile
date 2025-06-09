FROM python:3.10

WORKDIR /usr/src/

RUN apt install git

#RUN git clone https://github.com/impossible-bosses/ibce-bots

COPY . /usr/src/ibce-bots/

WORKDIR /usr/src/ibce-bots/

RUN apt-get update && apt-get install -y \
    libx11-xcb1 \
    curl \
    wget \
    gnupg \
    ca-certificates \
    libnss3 \
    libnspr4 \
    libdbus-1-3 \
    libatk1.0-0 \
    libatspi2.0-0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libxkbcommon0 \
    libasound2 \
    libgtk-3-0 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt && playwright install

COPY constants.py ./

CMD [ "python", "./main.py" ]
