FROM python:3.12-slim

WORKDIR /app
COPY receiver_server.py /app/receiver_server.py

ENV RECEIVER_PORT=8080
EXPOSE 8080

CMD ["python", "/app/receiver_server.py"]
