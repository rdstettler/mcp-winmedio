# mcp-winmedio

An **MCP (Model Context Protocol) Server** that lets AI assistants (e.g. Claude)
interact with your **winmedio** library account.

winmedio is a library management platform used by many libraries – primarily in
German-speaking countries – for their online public access catalog (OPAC). This
server exposes your library account data as MCP tools so that any MCP-compatible
AI client can answer questions like:

- *"Which books do I currently have borrowed and when do they need to be returned?"*

---

## Features

| MCP Tool | Description |
|---|---|
| `get_rented_items` | List all currently borrowed media with due dates |

---

## Requirements

- Python 3.11+ **or** a container runtime (Podman / Docker)
- A winmedio library account (username + password)
- Your library's winmedio name (the path segment in the URL, e.g. `buelach`)

---

## Configuration

All configuration is done via **environment variables**:

| Variable | Required | Description |
|---|---|---|
| `LIBRARY_NAME` | ✅ | Library identifier in the URL path (e.g. `buelach` for `https://www.winmedio.net/buelach/api/…`) |
| `WINMEDIO_USERNAME` | ✅ | Library card number / username |
| `WINMEDIO_PASSWORD` | ✅ | Account password (plain text) |

---

## Running with Podman (recommended)

### 1. Build the container image

```bash
podman build -t mcp-winmedio .
```

### 2. Run the MCP server

```bash
podman run --rm -i \
  -e LIBRARY_NAME=buelach \
  -e WINMEDIO_USERNAME=your_card_number \
  -e WINMEDIO_PASSWORD=your_password \
  mcp-winmedio
```

The `-i` flag keeps stdin open, which is required for the stdio-based MCP transport.

### 3. Add to your MCP client

For **Claude Desktop** (`~/.config/claude/claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "winmedio": {
      "command": "podman",
      "args": [
        "run", "--rm", "-i",
        "-e", "LIBRARY_NAME=buelach",
        "-e", "WINMEDIO_USERNAME=your_card_number",
        "-e", "WINMEDIO_PASSWORD=your_password",
        "mcp-winmedio"
      ]
    }
  }
}
```

---

## Running without a container

### 1. Install

```bash
pip install .
```

### 2. Set environment variables

```bash
export LIBRARY_NAME=buelach
export WINMEDIO_USERNAME=your_card_number
export WINMEDIO_PASSWORD=your_password
```

### 3. Run

```bash
mcp-winmedio
```

Or directly:

```bash
python -m mcp_winmedio.server
```

### 4. Add to Claude Desktop

```json
{
  "mcpServers": {
    "winmedio": {
      "command": "mcp-winmedio",
      "env": {
        "LIBRARY_NAME": "buelach",
        "WINMEDIO_USERNAME": "your_card_number",
        "WINMEDIO_PASSWORD": "your_password"
      }
    }
  }
}
```

---

## Development

```bash
# Create a virtual environment
python -m venv .venv
source .venv/bin/activate

# Install in editable mode with all extras
pip install -e ".[dev]"

# Run tests
pytest
```

---

## License

MIT – see [LICENSE](LICENSE).

