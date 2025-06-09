FROM python:3.10

WORKDIR /usr/src/

RUN apt install git

#RUN git clone https://github.com/impossible-bosses/ibce-bots

RUN pip install --upgrade pip

COPY ./requirements.txt /usr/src/ibce-bots/requirements.txt

RUN pip install --no-cache-dir -r requirements.txt && playwright install-deps && playwright install


COPY . /usr/src/ibce-bots/

WORKDIR /usr/src/ibce-bots/

COPY constants.py ./

CMD [ "python", "./main.py" ]
