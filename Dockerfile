FROM ghcr.io/astral-sh/uv:debian
WORKDIR /app
COPY . /app
RUN uv sync --locked
ENTRYPOINT ["uv", "run",  "-m",  "dozer"]
