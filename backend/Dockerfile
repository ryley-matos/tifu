FROM python:3.8-slim-buster

RUN apt-get update \
&& apt-get install libssl-dev gcc -y \
&& apt-get clean

COPY requirements.txt requirements.txt
RUN pip3 install -r requirements.txt

COPY . .

CMD ["sh", "run.sh"]
