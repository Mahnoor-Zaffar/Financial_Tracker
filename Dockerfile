FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN adduser --disabled-password --gecos "" appuser

COPY requirements.txt /app/requirements.txt
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY . /app
RUN mkdir -p /app/instance && chown -R appuser:appuser /app

USER appuser

EXPOSE 4848

CMD ["sh", "-c", "flask db upgrade && gunicorn --bind 0.0.0.0:${PORT:-4848} app:app"]
