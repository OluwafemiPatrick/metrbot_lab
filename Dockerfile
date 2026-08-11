FROM python:3.11-slim-bookworm AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /build

COPY pyproject.toml README.md LICENSE ./
COPY src ./src

RUN python -m pip wheel --no-deps --wheel-dir /wheels .


FROM python:3.11-slim-bookworm AS runtime

ENV HOME=/tmp \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY --from=builder /wheels /wheels
RUN python -m pip install --no-deps /wheels/*.whl && rm -rf /wheels

RUN mkdir -p /workspace && chown 10001:10001 /workspace
WORKDIR /workspace
USER 10001:10001

ENTRYPOINT ["metrbot-lab"]
CMD ["--help"]
