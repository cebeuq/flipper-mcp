# Python MCP SDK 1.27.x + FastMCP — verified reference

Everything below was verified by direct introspection of the **installed package `mcp==1.27.2`** (Python 3.12, Windows), plus the official v1.27.2 README and the Claude Code MCP docs. Signatures and behaviors quoted are the actual shipped code, not guesses.

---

## 1. The modern idiomatic FastMCP server

In the official SDK 1.x, FastMCP is **bundled** (it absorbed the original standalone `fastmcp` 1.0 back at SDK v1.2). Install with `pip install "mcp[cli]"` (or `uv add "mcp[cli]"`). The `[cli]` extra gives you the `mcp` CLI (`mcp dev`, `mcp run`, `mcp install`).

```python
from mcp.server.fastmcp import FastMCP

# name is positional; instructions is a system-prompt-like hint for clients
mcp = FastMCP("flipper", instructions="Control a Flipper Zero over its serial CLI.")


@mcp.tool()
def ir_send(protocol: str, address: int, command: int) -> str:
    """Send an infrared signal using the given protocol, address and command."""
    ...
    return "sent"
```

Key facts (verified against 1.27.2 source):

- **`@mcp.tool()` requires the parentheses.** Bare `@mcp.tool` raises `TypeError("The @tool decorator was used incorrectly. Did you forget to call it? Use @tool() instead of @tool")`. (The *standalone* PrefectHQ `fastmcp` 2.x package allows bare `@mcp.tool`; the official SDK 1.x does not.)
- Decorator signature: `tool(self, name=None, title=None, description=None, annotations=None, icons=None, meta=None, structured_output=None)`.
- **Type hints → input schema**: parameter annotations are turned into a Pydantic model, which produces the JSON `inputSchema`. E.g. `def echo(text: str)` produces `{"properties": {"text": {"title": "Text", "type": "string"}}, "required": ["text"], "type": "object"}`. Defaults become optional parameters; `Annotated[...]`/`Field(description=...)` add per-parameter descriptions. Inputs are validated before your function runs.
- **Docstring → description**: the function docstring becomes the tool `description` (overridable via `description=`). Function name becomes the tool name (overridable via `name=`).
- Both `def` and `async def` tools are supported.
- **Return values → content** (exact conversion logic in `mcp/server/fastmcp/utilities/func_metadata.py::_convert_to_content`):
  - `str` → one `TextContent`
  - `Image` / `Audio` helper → `ImageContent` / `AudioContent`
  - any `ContentBlock` (e.g. `mcp.types.TextContent`, `ImageContent`) → passed through
  - `list`/`tuple` → flattened, each item converted (so you can return `[Image(...), "caption"]`)
  - anything else (dict, dataclass, Pydantic model, int, …) → JSON-serialized `TextContent`
- **Structured output (added in SDK 1.10, spec 2025-06-18)**: if the return annotation is JSON-schema-able, FastMCP *also* auto-generates an `outputSchema` and returns `structuredContent`. Primitives get wrapped: `-> str` produces `outputSchema {"properties": {"result": {"type": "string"}}, "required": ["result"]}` and `structuredContent {"result": "..."}`. `-> dict[...]`, TypedDicts, dataclasses and Pydantic models map naturally. Return types that can't be serialized (like `Image`) simply get **no** output schema — the tool is unstructured, which is what you want for screenshots. You can force behavior with `@mcp.tool(structured_output=False)` (or `True`).

Full `FastMCP.__init__` signature in 1.27.2 (for reference — you'll normally only use `name`, `instructions`, and `lifespan` for a stdio server):

```
FastMCP(name=None, instructions=None, website_url=None, icons=None,
        auth_server_provider=None, token_verifier=None, event_store=None,
        retry_interval=None, *, tools=None, debug=False, log_level='INFO',
        host='127.0.0.1', port=8000, mount_path='/', sse_path='/sse',
        message_path='/messages/', streamable_http_path='/mcp',
        json_response=False, stateless_http=False,
        warn_on_duplicate_resources=True, warn_on_duplicate_tools=True,
        warn_on_duplicate_prompts=True, dependencies=(), lifespan=None,
        auth=None, transport_security=None)
```

Settings can also come from `FASTMCP_`-prefixed env vars or a `.env` file (pydantic-settings, `env_prefix='FASTMCP_'`).

---

## 2. Running over stdio + entrypoint pattern

`FastMCP.run` signature (verified): `run(self, transport: Literal['stdio', 'sse', 'streamable-http'] = 'stdio', mount_path: str | None = None) -> None`. It is **synchronous** and internally does `anyio.run(self.run_stdio_async)` — do not call it from an already-running event loop (use `await mcp.run_stdio_async()` there instead).

Single-file script:

```python
# flipper_server.py
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("flipper")

# ... @mcp.tool() definitions ...

if __name__ == "__main__":
    mcp.run()                      # stdio is the default
    # equivalently: mcp.run(transport="stdio")
```

Package layout (recommended for `python -m flipper_mcp`):

```
flipper_mcp/
├── __init__.py      # defines `mcp = FastMCP("flipper")` and the tools
└── __main__.py
```

```python
# flipper_mcp/__main__.py
from flipper_mcp import mcp

mcp.run()
```

Then `python -m flipper_mcp` starts the stdio server. Dev tooling: `mcp dev flipper_server.py` (Inspector UI), `mcp run flipper_server.py` (looks for a `mcp`/`server`/`app` object).

**Critical stdio rule**: never `print()` to stdout in a stdio server — stdout is the protocol channel. Log to stderr (`logging` defaults there) or use `await ctx.info(...)` to send MCP log notifications to the client. On Windows the SDK uses `pywin32>=310` for stdio pipes (installed automatically as a dependency).

---

## 3. Returning images (Flipper screenshot PNG)

The exact type is **`mcp.server.fastmcp.Image`** — a helper whose verified constructor is `Image(path: str | Path | None = None, data: bytes | None = None, format: str | None = None)`. Provide **exactly one** of `path`/`data` (both or neither raises `ValueError`). `format="png"` → `mimeType="image/png"`; with `path`, MIME is inferred from the extension (`.png`, `.jpg/.jpeg`, `.gif`, `.webp`); with raw `data` and no `format`, it defaults to `image/png`. FastMCP converts it to a spec `ImageContent` block with base64 `data` — you never base64 anything yourself.

```python
from mcp.server.fastmcp import Context, FastMCP, Image

mcp = FastMCP("flipper")


@mcp.tool()
async def screenshot(ctx: Context) -> Image:
    """Capture the Flipper Zero's current screen as a PNG image."""
    png_bytes: bytes = await capture_flipper_screen(ctx)  # your serial logic
    return Image(data=png_bytes, format="png")
```

From a file on disk instead:

```python
@mcp.tool()
def screenshot_file() -> Image:
    """Return the last saved Flipper screenshot."""
    return Image(path=r"C:\flipper\shot.png")   # mime inferred from .png
```

Verified end-to-end: a tool annotated `-> Image` produces `outputSchema: null` (unstructured, correct) and the call result is `[ImageContent(type='image', data='<base64>', mimeType='image/png')]`. To return an image **plus** text, return a list: `return [Image(data=png, format="png"), f"Screen captured at {ts}"]` (annotate `-> list` or drop the annotation). Equivalent lower-level alternative: build `mcp.types.ImageContent(type="image", data=base64.b64encode(png).decode(), mimeType="image/png")` yourself — `Image` is just the ergonomic wrapper. There is also an `Audio` helper with the same shape.

---

## 4. Lifespan / persistent state (the serial port)

The recommended pattern is the **`lifespan` async context manager**, passed to the constructor. Its verified type: `lifespan: Callable[[FastMCP], AbstractAsyncContextManager[LifespanResultT]]`. It runs once at server startup, the yielded object is available in every tool via `ctx.request_context.lifespan_context`, and the cleanup after `yield` runs on shutdown (including Ctrl-C / client disconnect).

```python
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

import serial  # pyserial

from mcp.server.fastmcp import Context, FastMCP, Image


@dataclass
class AppContext:
    port: serial.Serial


@asynccontextmanager
async def lifespan(server: FastMCP) -> AsyncIterator[AppContext]:
    """Open the Flipper serial port once; close it on shutdown."""
    port = serial.Serial("COM5", 230400, timeout=2)
    try:
        yield AppContext(port=port)
    finally:
        port.close()


mcp = FastMCP("flipper", lifespan=lifespan)


@mcp.tool()
def run_cli(command: str, ctx: Context) -> str:
    """Run a raw Flipper CLI command and return its output."""
    app: AppContext = ctx.request_context.lifespan_context
    app.port.write((command + "\r\n").encode())
    return app.port.read_until(b">: ").decode(errors="replace")
```

Notes (all verified against 1.27.2):

- Getting the `Context`: add a parameter annotated `Context` to the tool (any parameter name works; detection is by annotation). It's optional — omit it if unused. It's excluded from the input schema.
- `Context` also gives you `await ctx.info/debug/warning/error(msg)` (these are **async** — must be awaited), `await ctx.report_progress(cur, total, message)`, `ctx.request_id`, `await ctx.read_resource(uri)`, `await ctx.elicit(...)`.
- A **module-level global is also perfectly fine** for a single-process stdio server (one client, one process). A common pragmatic hybrid: a global holding a lazily-opened connection, so the server starts even when the device is unplugged, and each tool (re)connects on demand:

```python
_port: serial.Serial | None = None

def get_port() -> serial.Serial:
    global _port
    if _port is None or not _port.is_open:
        _port = serial.Serial("COM5", 230400, timeout=2)
    return _port
```

The lifespan approach is the documented/recommended one (typed, testable, guaranteed cleanup); the global is acceptable and avoids failing at startup if the device is absent. Caution: pyserial is blocking — for long reads inside `async def` tools, wrap in `await anyio.to_thread.run_sync(...)` so you don't block the event loop (sync `def` tools are already run appropriately).

---

## 5. Error handling

Verified flow in 1.27.2:

1. Any exception raised inside your tool function is caught by `Tool.run` and re-raised as `ToolError(f"Error executing tool {name}: {e}")`.
2. The low-level server's `call_tool` handler catches it and returns `CallToolResult(isError=True, content=[TextContent(text=str(e))])`.

So: **just `raise`**. Exceptions never crash the server, and never surface as JSON-RPC protocol errors — they become an in-band tool result with `isError: true` whose text is the exception message, which the model (Claude) sees and can react to.

```python
from mcp.server.fastmcp.exceptions import ToolError

@mcp.tool()
def read_file_from_flipper(path: str, ctx: Context) -> str:
    """Read a file from the Flipper's storage."""
    if not path.startswith("/ext/") and not path.startswith("/int/"):
        raise ToolError("path must start with /ext/ or /int/")   # clean message
    ...
```

Practical guidance:

- Raise `ToolError` (from `mcp.server.fastmcp.exceptions`) for expected failures — pass-through message. Available exceptions: `FastMCPError` (base), `ValidationError`, `ResourceError`, `ToolError`, `InvalidSignature`.
- Any other exception works too; the client sees `"Error executing tool <name>: <message>"`. Make messages actionable (`"Flipper not found on COM5 — is qFlipper open and holding the port?"`) since the model uses them to self-correct.
- Returning error text as a normal string also "works" but doesn't set `isError`, so the model can't distinguish failure from output — prefer raising.
- Input validation failures (wrong argument types) are handled by the SDK before your function runs and returned as errors automatically.

---

## 6. Registering with Claude Code / Claude Desktop on Windows

**Important caveat (verified via docs + open bug):** the `cwd` field for stdio servers is documented in Claude Code's plugin reference but is **ignored** for regular `.mcp.json`/`claude mcp add` servers ([issue #17565](https://github.com/anthropics/claude-code/issues/17565)); Claude Desktop ignores it too. **Do not depend on the working directory.** Make the server importable regardless: either (a) `pip install -e .` the package into the interpreter you reference, (b) set `PYTHONPATH` in `env`, or (c) launch a script by absolute path. Also always use the **absolute path to python.exe** (or `py.exe`) — the GUI/desktop processes may not have your venv on PATH.

### Option A — `claude mcp add` (CLI)

```powershell
# user scope (all your projects); everything after -- is the server command
claude mcp add --transport stdio --scope user flipper -- python -m flipper_mcp

# safer: absolute interpreter + PYTHONPATH so `python -m` works from any cwd
claude mcp add --transport stdio --scope user --env PYTHONPATH=C:\Users\yairh\Desktop\flipper-mcp flipper -- C:\Users\yairh\Desktop\flipper-mcp\.venv\Scripts\python.exe -m flipper_mcp
```

Scopes: `--scope local` (default, this project only, stored in `~/.claude.json`), `--scope project` (writes `.mcp.json` in the project root, check-in-able, requires approval on first use), `--scope user` (all projects, `~/.claude.json`). The `--` separator is required so the server's own flags aren't parsed by the CLI, and don't place the server name immediately after `--env` (the CLI would read it as another KEY=value). Verify with `claude mcp list` / `claude mcp get flipper`, or `/mcp` inside a session. No `cmd /c` wrapper is needed for a real `.exe` like `python.exe` (that workaround is for `.cmd` shims like `npx`).

### Option B — `.mcp.json` in the project root (project scope)

```json
{
  "mcpServers": {
    "flipper": {
      "type": "stdio",
      "command": "C:\\Users\\yairh\\Desktop\\flipper-mcp\\.venv\\Scripts\\python.exe",
      "args": ["-m", "flipper_mcp"],
      "env": {
        "PYTHONPATH": "C:\\Users\\yairh\\Desktop\\flipper-mcp",
        "FLIPPER_COM_PORT": "COM5"
      }
    }
  }
}
```

Script-path variant (no packaging or PYTHONPATH needed):

```json
{
  "mcpServers": {
    "flipper": {
      "type": "stdio",
      "command": "C:\\Users\\yairh\\Desktop\\flipper-mcp\\.venv\\Scripts\\python.exe",
      "args": ["C:\\Users\\yairh\\Desktop\\flipper-mcp\\flipper_server.py"]
    }
  }
}
```

JSON notes: backslashes must be escaped (`\\`); `${VAR}` / `${VAR:-default}` expansion is supported in `command`, `args`, and `env`; an optional per-server `"timeout"` (ms) overrides `MCP_TOOL_TIMEOUT`; Claude Code sets `CLAUDE_PROJECT_DIR` in the spawned server's environment (read it with `os.environ["CLAUDE_PROJECT_DIR"]` if you want project-relative behavior without cwd). One-liner equivalent: `claude mcp add-json flipper '{"type":"stdio","command":"C:\\...\\python.exe","args":["-m","flipper_mcp"],"env":{"PYTHONPATH":"C:\\...\\flipper-mcp"}}'`.

### Option C — Claude Desktop (`claude_desktop_config.json`)

File: `%APPDATA%\Claude\claude_desktop_config.json` (e.g. `C:\Users\yairh\AppData\Roaming\Claude\claude_desktop_config.json`). Same `mcpServers` shape, no `type` field needed (stdio only):

```json
{
  "mcpServers": {
    "flipper": {
      "command": "C:\\Users\\yairh\\Desktop\\flipper-mcp\\.venv\\Scripts\\python.exe",
      "args": ["-m", "flipper_mcp"],
      "env": { "PYTHONPATH": "C:\\Users\\yairh\\Desktop\\flipper-mcp" }
    }
  }
}
```

Shortcut: `mcp install flipper_server.py --name flipper` (from `mcp[cli]`) writes this file for you. `claude mcp add-from-claude-desktop` (importing Desktop config into Claude Code) works only on macOS/WSL, not native Windows.

---

## 7. Changes / deprecations relevant to 1.27.x

- **`mcp` requires Python >= 3.10** (verified from package metadata). 1.27.2 deps include `pydantic>=2.11,<3`, `httpx<1.0`, `jsonschema>=4.20`, and `pywin32>=310` on Windows.
- **FastMCP lives in the official SDK** since v1.2 (Dec 2024): `from mcp.server.fastmcp import FastMCP`. The PyPI package `fastmcp` (PrefectHQ, v2.x) is a *different, independently maintained* project with a diverged API (bare `@mcp.tool`, `Client`, middleware, etc.) — don't mix its docs with the official SDK's.
- **Structured output** (SDK 1.10, spec 2025-06-18): return-type annotations now auto-generate `outputSchema` and `structuredContent`; primitives are wrapped as `{"result": ...}`. Older SDKs sent text content only. If a client complains about output validation, set `structured_output=False` on the tool.
- **Transports**: `streamable-http` was added in 1.8 and is the recommended remote transport; **SSE is deprecated** in favor of it (still accepted by `run()` in 1.27). The **WebSocket transport is deprecated in v1.28.0** (was never in the spec). For your use case, stdio is unaffected and remains the default.
- **`Context` logging methods are async** (`await ctx.info(...)`) — older snippets show sync calls; those will silently no-op (unawaited coroutine) on 1.27.
- **Lifespan receives the `FastMCP` instance** as its single argument and its yield is reached via `ctx.request_context.lifespan_context` — this is the stable 1.x pattern.
- 1.27.0 (Apr 2026) itself added: RFC 8707 OAuth resource validation, StreamableHTTP idle timeout, tasks capability backport, command-injection hardening — none affect the FastMCP stdio surface above. 1.27.1/1.27.2 were compat/auth patches.
- **v2 is coming (beta since June 2026, GA targeted ~2026-07-28 spec)**: the bundled class is renamed **`FastMCP` → `MCPServer`** (`from mcp.server.mcpserver import MCPServer`), with a stateless core and constructor-based low-level API. Everything in this document is the 1.x API. **Pin `mcp>=1.27,<2`** in your project so a future `pip install -U` doesn't break the imports. (Context7's `/modelcontextprotocol/python-sdk` docs already track the v2/main branch — its `mcp.server.mcpserver` snippets will NOT import on 1.27.x.)
- Additive niceties available by 1.27 you may see in docs but can ignore: `title=`, `icons=`, `meta=`, `annotations=` (e.g. `ToolAnnotations(readOnlyHint=True)`) on `@mcp.tool()`; `website_url=`/`icons=` on the constructor; `Audio` helper; elicitation (`ctx.elicit`).

Sources: [MCP Python SDK repo/README](https://github.com/modelcontextprotocol/python-sdk) | [python-sdk releases](https://github.com/modelcontextprotocol/python-sdk/releases) | [SDK betas for 2026-07-28 spec (MCP blog)](https://blog.modelcontextprotocol.io/posts/sdk-betas-2026-07-28/) | [mcp on PyPI](https://pypi.org/project/mcp/) | [Claude Code MCP docs](https://code.claude.com/docs/en/mcp) | [claude-code issue #17565 (cwd ignored)](https://github.com/anthropics/claude-code/issues/17565) | [PrefectHQ/fastmcp (standalone v2)](https://github.com/PrefectHQ/fastmcp) | [fastmcp on PyPI](https://pypi.org/project/fastmcp/)