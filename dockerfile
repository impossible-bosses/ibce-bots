FROM python:3.10

WORKDIR /usr/src/

RUN apt install git

RUN git clone https://github.com/impossible-bosses/ibce-bots

WORKDIR /usr/src/ibce-bots/

RUN pip install --no-cache-dir -r requirements.txt

COPY params.py ./
COPY constants.py ./

CMD [ "python", "./main.py" ]
