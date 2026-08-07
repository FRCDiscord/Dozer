FROM ghcr.io/astral-sh/uv:0.12.1 AS uv
FROM python:3.10.19
WORKDIR /app
COPY --from=uv /uv /uvx /bin/
COPY pyproject.toml uv.lock /app/
RUN uv export --frozen --no-dev --no-emit-project --no-hashes -o /tmp/requirements.txt \
    && uv pip install --system --no-cache -r /tmp/requirements.txt
COPY . /app
ENTRYPOINT ["python3", "-m",  "dozer"]
