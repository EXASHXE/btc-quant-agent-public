FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
COPY configs ./configs
RUN pip install --no-cache-dir -e '.[api,live]'

RUN useradd --create-home --uid 10001 quant && mkdir -p /app/var && chown -R quant:quant /app
USER quant

CMD ["uvicorn", "btc_quant_agent.api:app", "--host", "0.0.0.0", "--port", "8787", "--workers", "1"]
