FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.31.1 /uv /usr/local/bin/uv

WORKDIR /app
COPY app.py .

RUN uv pip install --system --no-cache bottle==0.13.4 gunicorn redis

EXPOSE 12345

CMD ["gunicorn", "--bind", "0.0.0.0:12345", "--workers", "4", "app:app"]
