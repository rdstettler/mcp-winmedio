# Containerfile for mcp-winmedio
# Build:  podman build -t mcp-winmedio .
# Run:    podman run --rm -i \
#           -e WINMEDIO_BASE_URL=https://opac.winmedio.net/MyCity \
#           -e WINMEDIO_USERNAME=your_card_number \
#           -e WINMEDIO_PASSWORD=your_password \
#           mcp-winmedio

FROM python:3.12-slim

WORKDIR /app

# Install build tools needed for Python packages
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy project files
COPY pyproject.toml README.md ./
COPY src/ ./src/

# Install the package and its dependencies
RUN pip install --no-cache-dir .

# Environment variables (must be supplied at runtime)
ENV WINMEDIO_BASE_URL=""
ENV WINMEDIO_USERNAME=""
ENV WINMEDIO_PASSWORD=""

# Run the MCP server over stdio
ENTRYPOINT ["mcp-winmedio"]
