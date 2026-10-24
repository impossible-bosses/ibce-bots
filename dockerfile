FROM python:3.10

WORKDIR /usr/src/

# git is already present in the full python:3.10 image (needed by gitpython)

#RUN git clone https://github.com/impossible-bosses/ibce-bots

COPY . /usr/src/ibce-bots/

WORKDIR /usr/src/ibce-bots/

RUN pip install --no-cache-dir -r requirements.txt

COPY constants.py ./

CMD [ "python", "./main.py" ]
