FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
COPY configs ./configs
RUN pip install --no-cache-dir -e '.[api]'

RUN useradd --create-home --uid 10001 quant && mkdir -p /app/var && chown -R quant:quant /app
USER quant

CMD ["quantctl", "daemon"]
