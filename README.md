# mcp-winmedio

An **MCP (Model Context Protocol) Server** that lets AI assistants (e.g. Claude)
interact with your **winmedio** library account.

winmedio is a library management platform used by many libraries – primarily in
German-speaking countries – for their online public access catalog (OPAC). This
server exposes your library account data as MCP tools so that any MCP-compatible
AI client can answer questions like:

- *"Which books do I currently have borrowed and when do they need to be returned?"*
- *"Are there any books by Douglas Adams available in the library?"*
- *"Please renew item 1234567 for me."*

---

## Features

| MCP Tool | Description |
|---|---|
| `get_rented_items` | List all currently borrowed media with due dates |
| `get_reservations` | List active reservations with queue position |
| `get_account_info` | Show account name, card validity, and open fees |
| `search_catalog` | Search the library catalog by title, author, or ISBN |
| `renew_item` | Attempt to renew a borrowed item by its copy number |

---

## Requirements

- Python 3.11+ **or** a container runtime (Podman / Docker)
- A winmedio OPAC account (library card number + password)
- The base URL of your library's winmedio portal
  (e.g. `https://opac.winmedio.net/MyCity` or `https://mylib.winmedio.net/webopac`)

---

## Configuration

All configuration is done via **environment variables**:

| Variable | Required | Description |
|---|---|---|
| `WINMEDIO_BASE_URL` | ✅ | Base URL of your library's winmedio portal |
| `WINMEDIO_USERNAME` | ✅ | Library card number / username |
| `WINMEDIO_PASSWORD` | ✅ | Account password |

---

## Running with Podman (recommended)

### 1. Build the container image

```bash
podman build -t mcp-winmedio .
```

### 2. Run the MCP server

```bash
podman run --rm -i \
  -e WINMEDIO_BASE_URL=https://opac.winmedio.net/MyCity \
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
        "-e", "WINMEDIO_BASE_URL=https://opac.winmedio.net/MyCity",
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
export WINMEDIO_BASE_URL=https://opac.winmedio.net/MyCity
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
        "WINMEDIO_BASE_URL": "https://opac.winmedio.net/MyCity",
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

## Finding your library's winmedio URL

Most winmedio portals follow one of these URL patterns:

- `https://opac.winmedio.net/<CityName>`
- `https://<city>.winmedio.net/webopac`
- `https://www.winmedio.net/<city>/`

Search for your library name together with "winmedio" or "webopac" to find the
correct URL.  The login page is usually reachable at the root or at
`Default.aspx` / `index.aspx`.

---

## License

MIT – see [LICENSE](LICENSE).

