FROM mcr.microsoft.com/playwright:v1.50.1-noble

WORKDIR /app

COPY . /app

RUN mkdir -p /app/reports

RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-pip

RUN pip install --no-cache-dir --break-system-packages -r requirements.txt

# Run post-installation setup
RUN crawl4ai-setup

# Verify your installation, but ignore potential error exit code (Its give 1 for success 🤔)
RUN crawl4ai-doctor || true
RUN echo "Crawl4AI Doctor Exit Code: $?"

# Expose port 9090
EXPOSE 9090

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_DEFAULT_TIMEOUT=100 \
    DEBIAN_FRONTEND=noninteractive

ENTRYPOINT ["streamlit", "run", "ui.py", "--server.port=9090", "--server.address=0.0.0.0"]
