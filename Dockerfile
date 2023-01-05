FROM python:3.11-alpine3.17

WORKDIR /app

RUN apk update && apk add pkgconfig python3-dev build-base cairo-dev cairo cairo-tools git

COPY requirements.txt ./

RUN pip install --no-cache-dir -r requirements.txt

COPY python_nostr/requirements.txt ./python_nostr/requirements.txt

RUN pip install --no-cache-dir -r python_nostr/requirements.txt

EXPOSE 5000

COPY . .

CMD [ "python", "cli.py" ]