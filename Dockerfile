FROM python:3.11-slim

WORKDIR /srv/sniper

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/srv/sniper

RUN useradd --create-home --shell /bin/bash sniper_user && \
    mkdir -p /srv/sniper/data /srv/sniper/data/backups && \
    chown -R sniper_user:sniper_user /srv/sniper

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=sniper_user:sniper_user . .

USER sniper_user

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
