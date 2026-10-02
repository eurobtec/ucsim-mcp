# ucsim-mcp

A [Model Context Protocol](https://modelcontextprotocol.io) (MCP) server for the
[µCsim](http://www.ucsim.hu) microcontroller simulator, built with
[FastMCP](https://github.com/jlowin/fastmcp). It lets an AI model (or any MCP
client) load firmware images, reset/run/step a simulated CPU, inspect and modify
memory and registers, set breakpoints, and drive peripherals on virtual
hardware targets — the whole `ucsim_*` family (`ucsim_51`/`s51`, `ucsim_z80`,
`ucsim_stm8`, …).

## How it works

The server is a thin adapter over the [**pyucsim**](../pyucsim) client library,
which does the actual simulator driving: it holds one long-lived `ucsim_*`
process per **session**, driven over a pseudo-terminal with a unique prompt
marker (ucSim only prints its prompt on a TTY).

`pyucsim` handles several ucSim quirks transparently:

- **`@` in a filename crashes ucSim** (it parses `file@memoryspace`). Images
  whose path contains `@` — e.g. `M2764A@DIP28.HEX` — are copied to a safe temp
  path before loading.
- **`run N` does not stop after N cycles** on the MCS-51 build (it free-runs
  until a breakpoint). Use the `step` tool for a bounded, deterministic advance.
- **Commands are never pipelined** after a `run`/`step`, which ucSim would
  otherwise swallow as a user interrupt.

```
MCP client ──stdio──▶ ucsim-mcp (FastMCP tools) ──▶ pyucsim.UCSimEngine ──pty──▶ ucsim_51
```

## Install

The simulator binary is **not** bundled — point the server at your own ucSim
build. (A `ucsim_*` / `s51` binary is auto-discovered on `PATH`, then a local
build at `~/github/razr/ucsim/src/sims/s51.src/ucsim_51`.)

This package depends on the **pyucsim** library. Until both are published, install
pyucsim from its sibling checkout first:

```bash
cd ucsim-mcp
python3 -m venv .venv
. .venv/bin/activate
pip install -e ../pyucsim        # the client library (dependency)
pip install -e ".[dev]"          # the MCP server
```

## Configuration

Environment variables set the defaults for new sessions:

| Variable        | Meaning                                   | Example                 |
| :-------------- | :---------------------------------------- | :---------------------- |
| `UCSIM_BINARY`  | ucSim executable (path or name on `PATH`) | `/usr/local/bin/ucsim_51` |
| `UCSIM_CPU`     | default CPU type (`-t`)                   | `8031`                  |
| `UCSIM_XTAL`    | default crystal frequency (`-X`)          | `11.0592M`              |

Any of these can be overridden per-session via `start_session` arguments.

## Run

```bash
# stdio transport (what MCP clients spawn)
python -m ucsim_mcp
# or, after install:
ucsim-mcp
```

### MCP client configuration

The repo ships a ready-to-use [`mcp.json`](mcp.json) that invokes the
`ucsim-mcp` console script by name — **no hardcoded paths**. For this to work
the client must find `ucsim-mcp` on its `PATH`. The portable way to do that is
to install it in an isolated environment with [pipx](https://pipx.pypa.io):

```bash
pipx install /path/to/ucsim-mcp        # or: pipx install ucsim-mcp (once published)
```

```json
{
  "mcpServers": {
    "ucsim": {
      "command": "ucsim-mcp",
      "args": [],
      "env": {
        "UCSIM_CPU": "51",
        "UCSIM_XTAL": "11.0592M"
      }
    }
  }
}
```

`UCSIM_BINARY` is **optional** — the server auto-discovers a `ucsim_*` / `s51`
binary on `PATH`. Set it only if your simulator lives somewhere unusual.

**No install (run from a checkout)** — use `pipx run` / `uvx` so the client
needs no fixed venv path:

```json
{
  "mcpServers": {
    "ucsim": {
      "command": "pipx",
      "args": ["run", "--spec", "/path/to/ucsim-mcp", "ucsim-mcp"]
    }
  }
}
```

(Replace `pipx run --spec ... ucsim-mcp` with `uvx --from /path/to/ucsim-mcp
ucsim-mcp` if you prefer `uv`.)

## Tools

| Tool                | Purpose                                                     |
| :------------------ | :---------------------------------------------------------- |
| `start_session`     | Start a simulator process (optionally load an image)        |
| `list_sessions`     | List active sessions and their configuration                |
| `stop_session`      | Terminate a session                                         |
| `load_image`        | Load a firmware image into a running session                |
| `reset`             | Reset the CPU                                               |
| `step`              | Advance a **bounded** number of instructions (`step N`)     |
| `run`               | Free-run until a breakpoint / stop / timeout                |
| `stop_run`          | Interrupt a free-running simulation (SIGINT)                |
| `get_state`         | CPU state summary (PC, cycles, …)                           |
| `get_registers`     | Dump CPU registers                                          |
| `read_memory`       | `dump <space> <start> <end>`                                |
| `write_memory`      | `set mem <space> <addr> <value>`                            |
| `disassemble`       | Disassemble from an address or the current PC               |
| `set_breakpoint`    | Set an execution breakpoint                                 |
| `clear_breakpoint`  | Clear an execution breakpoint                               |
| `list_breakpoints`  | List breakpoints                                            |
| `load_hardware`     | Load a cl_hw plugin `.so` at runtime (`loadhw`)             |
| `list_hardware`     | List loaded plugins + ucSim's `info hardware`               |
| `set_hardware`      | Drive a peripheral (`set hardware …`, incl. cl_hw plugins)  |
| `ucsim_command`     | Escape hatch: run any raw ucSim console command             |

Memory `space` names depend on the simulated CPU (for MCS-51: `rom`/`code`,
`iram`, `xram`, `sfr`).

## Hardware plugins (cl_hw)

ucSim peripherals can be loaded at runtime as shared objects built against the
ucsim-plugin-sdk (`loadhw`, alias `insmod`). Two ways:

- **At startup** (recommended when the module must observe the first fetch):
  `start_session(image=..., load_hw=["/path/adc.so", "/path/teachbox.so"])`.
  Modules are loaded *before* the image and reset.
- **At runtime**: `load_hardware(session_id, "/path/adc.so")`. Returns the
  parsed `id_string`; drive it with `set_hardware(session_id, "adc 0 0x80")`.

The plugin must be built against the **same** ucSim binary (the C++ ABI must
match). `list_hardware` shows what's loaded.

## Example flow

```
start_session(image="firmware.hex", cpu="51", xtal="11.0592M")  -> {"session_id": "sim1", ...}
reset(session_id="sim1")
read_memory(session_id="sim1", space="rom", start=0, end=15)
step(session_id="sim1", count=100)
get_state(session_id="sim1")
write_memory(session_id="sim1", space="iram", address=0x50, value=0x42)
stop_session(session_id="sim1")
```

## Tests

```bash
. .venv/bin/activate
python -m pytest
```

Unit tests run without a simulator. Integration tests drive the real binary and
auto-skip if `UCSIM_BINARY` (default: the local `ucsim_51` build) or the test
ROM is unavailable.

## License

MIT.
