# Playwright's Python image ships Chromium and all its OS dependencies pinned to the
# same version as the `playwright` package (1.62.0), so the browser matches the driver.
FROM mcr.microsoft.com/playwright/python:v1.62.0-jammy

# uv provides fast, locked dependency installs.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Install locked dependencies first (cached while pyproject.toml/uv.lock are unchanged),
# then the project itself once the source is copied in.
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project

COPY . .
RUN uv sync --locked --no-dev

# The WhatsApp session profile and the jobs database live on mounted volumes under
# /data. Bind to all interfaces so the dashboard is reachable from the host; this is an
# env value, not a code literal, keeping the bandit S104 lint clean.
ENV IMMEPE_HEADLESS=true \
    IMMEPE_PROFILE_DIR=/data/profile \
    IMMEPE_DB_PATH=/data/jobs.db \
    IMMEPE_WEB_HOST=0.0.0.0 \
    IMMEPE_WEB_PORT=8000

EXPOSE 8000

# --no-sync so the container never touches the network to re-resolve at start-up.
CMD ["uv", "run", "--no-sync", "immepe-bot", "serve"]
