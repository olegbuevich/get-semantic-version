FROM python:3.12-alpine

RUN apk add --no-cache git \
      && git config --global --add safe.directory '*'
WORKDIR /action
COPY requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY src ./src
ENTRYPOINT [ "python", "/action/src/app.py" ]
