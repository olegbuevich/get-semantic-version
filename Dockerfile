FROM python:3.12-alpine

RUN apk add --no-cache git
WORKDIR /action
COPY requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY src ./src
USER 1001
ENTRYPOINT [ "python", "/action/src/app.py" ]
