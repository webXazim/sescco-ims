FROM python:3.13-slim AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /build
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements/base.txt requirements/production.txt /build/requirements/
RUN pip install --upgrade pip \
    && pip install --requirement /build/requirements/production.txt

FROM python:3.13-slim AS runtime

ARG APP_UID=10001
ARG APP_GID=10001

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DJANGO_SETTINGS_MODULE=config.settings.production

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates libpq5 \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid "${APP_GID}" django \
    && useradd --uid "${APP_UID}" --gid django --create-home --shell /usr/sbin/nologin django

COPY --from=builder /opt/venv /opt/venv
COPY --chown=django:django . /app

RUN chmod 0755 /app/scripts/entrypoint.sh /app/scripts/*.sh \
    && mkdir -p /app/staticfiles /app/media \
    && chown -R django:django /app/staticfiles /app/media

USER django

ENTRYPOINT ["/app/scripts/entrypoint.sh"]
CMD ["gunicorn", "--config", "/app/deploy/gunicorn.conf.py", "config.wsgi:application"]
