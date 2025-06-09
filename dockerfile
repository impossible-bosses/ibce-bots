FROM python:3.10

WORKDIR /usr/src/

RUN apt install git

#RUN git clone https://github.com/impossible-bosses/ibce-bots

RUN pip install --upgrade pip

COPY ./requirements.txt /usr/src/ibce-bots/requirements.txt

WORKDIR /usr/src/ibce-bots/

RUN pip install --no-cache-dir -r requirements.txt && playwright install-deps && playwright install

COPY . ./

CMD [ "python", "./main.py" ]
