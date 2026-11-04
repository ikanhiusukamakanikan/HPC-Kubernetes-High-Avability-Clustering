FROM python:3.12-slim-bookworm
WORKDIR /app
COPY worker.py /app/worker.py
USER 1000:1000
ENTRYPOINT ["python", "-u", "/app/worker.py"]
