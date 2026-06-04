FROM python:3.11-slim

WORKDIR /app

ENV VIRTUAL_ENV=/opt/venv
ENV PATH=/opt/venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

# System deps: build tools + libGL pour PDF/vision (openingestion, PyMuPDF)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libgl1 \
    libglib2.0-0 \
    libgomp1 \
    libfontconfig1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

# NOTE: premier build ~15-20 min (openingestion[mineru] installe torch + transformers)
RUN python -m venv "$VIRTUAL_ENV" \
    && pip install --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Navigateurs Playwright pour le connecteur web (supprimer si non utilisé)
RUN playwright install chromium --with-deps

COPY . .

EXPOSE 8000

# CMD par défaut = API. Le worker surcharge cette commande dans docker-compose.prod.yml
CMD ["/opt/venv/bin/uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
