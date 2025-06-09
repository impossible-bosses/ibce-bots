FROM python:3.12

WORKDIR /usr/src/

RUN apt install git

#RUN git clone https://github.com/impossible-bosses/ibce-bots

COPY . /usr/src/ibce-bots/

WORKDIR /usr/src/ibce-bots/

RUN pip install --no-cache-dir -r requirements.txt

COPY constants.py ./

CMD [ "python", "./main.py" ]
