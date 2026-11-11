FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.11.8 /uv /usr/local/bin/uv

WORKDIR /app
COPY app.py etcdapi.py .

RUN uv pip install --system --no-cache bottle==0.13.4 gunicorn redis

EXPOSE 12345

# One process with threads: the strike/leader state (see the strike mode
# section of app.py) lives in the process memory, and delegation is a
# matter of blocking HTTP calls, a good fit for threads.
CMD ["gunicorn", "--bind", "0.0.0.0:12345", "--workers", "1", "--threads", "8", "--access-logfile", "-", "app:app"]
