FROM python:3.10-slim

WORKDIR /usr/src/

# git is required by gitpython (not included in the slim image)
RUN apt-get update && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

#RUN git clone https://github.com/impossible-bosses/ibce-bots

COPY . /usr/src/ibce-bots/

WORKDIR /usr/src/ibce-bots/

RUN pip install --no-cache-dir -r requirements.txt

COPY constants.py ./

CMD [ "python", "./main.py" ]
