FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY pyproject.toml .
COPY src/ src/
COPY tests/ tests/

RUN mkdir -p /app/data

RUN pip install --no-cache-dir pytest pytest-cov

EXPOSE 8080
HEALTHCHECK --interval=60s --timeout=10s --retries=3 CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health')" || exit 1

ENTRYPOINT ["python", "-m", "src.bot.main"]
