# The agent locates config/ and skills/ relative to its own source file, two
# levels up from src/scout/. A normal wheel install into site-packages would
# move that anchor and the agent would come up unable to find its own rubric, so
# the project is synced in place at /app and the layout is preserved.

FROM python:3.12-slim AS base

COPY --from=ghcr.io/astral-sh/uv:0.5 /uv /usr/local/bin/uv

WORKDIR /app

ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Dependencies first, so that editing the agent does not re-resolve the world.
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
RUN uv sync --extra serve --frozen --no-dev

COPY config ./config
COPY skills ./skills

# Nothing here needs root, and the process answers requests from the internet.
RUN useradd --create-home --uid 10001 scout && chown -R scout:scout /app
USER scout

ENV PATH="/app/.venv/bin:$PATH" \
    SCOUT_HOST=0.0.0.0 \
    SCOUT_PORT=8080

EXPOSE 8080

# No LinkedIn MCP in the image on purpose: the session it needs is a browser
# profile on the owner's machine, and shipping one into a container would mean
# baking a credential into an image and driving a bannable account from a public
# endpoint. The agent already degrades to the open listing and web search, and
# says so in its answers.
ENV SCOUT_LINKEDIN_MCP_COMMAND=""

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8080/health', timeout=4).status == 200 else 1)"

CMD ["scout-serve"]
