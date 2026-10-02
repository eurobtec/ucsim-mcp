"""FastMCP server exposing the µCsim simulator as MCP tools.

Configuration (environment variables):

* ``UCSIM_BINARY``   default ``ucsim_*`` executable (path or name on PATH).
                     Falls back to the user's local build, then ``s51``.
* ``UCSIM_CPU``      default CPU type for new sessions (e.g. ``51``, ``8031``).
* ``UCSIM_XTAL``     default crystal frequency (e.g. ``11.0592M``).

Run with::

    python -m ucsim_mcp            # stdio transport (for MCP clients)
"""
from __future__ import annotations

import os
import shutil

from fastmcp import FastMCP

from pyucsim import SessionManager, UCSimError

mcp = FastMCP(
    name="ucsim-mcp",
    instructions=(
        "Drive the µCsim microcontroller simulator (ucsim_51 / s51 and the "
        "other ucsim_* family binaries). Start a session with `start_session` "
        "(optionally loading a firmware image), then reset/step/run the CPU "
        "and inspect or modify memory, registers, and peripherals. For MCS-51 "
        "firmware use `step` (bounded) rather than `run` for a fixed number of "
        "cycles, because `run N` free-runs until a breakpoint. Use "
        "`ucsim_command` for any raw ucSim command not covered by a dedicated "
        "tool."
    ),
)

_sessions = SessionManager()


# -- configuration helpers ----------------------------------------------------
# Common ucSim family binaries to probe on PATH when UCSIM_BINARY is unset.
_KNOWN_BINARIES = (
    "ucsim_51", "s51", "ucsim_z80", "ucsim_stm8", "ucsim_avr",
    "ucsim_6809", "ucsim_mos6502", "ucsim_xa", "ucsim_tlcs",
)


def _default_binary() -> str:
    env = os.environ.get("UCSIM_BINARY")
    if env:
        return os.path.expanduser(env)
    # Prefer whatever ucSim family binary is on PATH.
    for name in _KNOWN_BINARIES:
        found = shutil.which(name)
        if found:
            return found
    # Last resort: a local source build (overridable with UCSIM_BINARY).
    local = os.path.expanduser(
        "~/github/razr/ucsim/src/sims/s51.src/ucsim_51")
    if os.path.exists(local):
        return local
    # Return a sensible name; start_session will raise a clear error if absent.
    return "s51"


def _default_cpu() -> str | None:
    return os.environ.get("UCSIM_CPU") or None


def _default_xtal() -> str | None:
    return os.environ.get("UCSIM_XTAL") or None


# -- session lifecycle --------------------------------------------------------
@mcp.tool
def start_session(
    image: str | None = None,
    cpu: str | None = None,
    xtal: str | None = None,
    binary: str | None = None,
    load_hw: list[str] | None = None,
    extra_args: list[str] | None = None,
    session_id: str | None = None,
) -> dict:
    """Start a new ucSim session (a long-lived simulator process).

    Args:
        image: Optional firmware image to load (Intel HEX / S19 / etc.). Paths
            containing ``@`` are copied to a safe temp path automatically.
        cpu: CPU type (``-t``), e.g. ``51``, ``8031``, ``Z80``. Defaults to
            ``UCSIM_CPU``.
        xtal: Crystal frequency (``-X``), e.g. ``11.0592M``. Defaults to
            ``UCSIM_XTAL``.
        binary: ucSim executable to use. Defaults to ``UCSIM_BINARY`` /
            local build / ``s51``.
        load_hw: Optional list of cl_hw plugin ``.so`` paths to load *before*
            the image/reset, so a module can observe the first fetch. Each
            must be built against the ucsim-plugin-sdk for this binary.
        extra_args: Additional raw CLI arguments passed before the image.
        session_id: Explicit id for the session (auto-generated if omitted).

    Returns:
        The session id, the resolved binary/cpu/xtal, the startup banner, and
        the list of loaded hardware modules (with their ``id_string``).
    """
    sid = _sessions.create(
        binary=binary or _default_binary(),
        cpu=cpu if cpu is not None else _default_cpu(),
        xtal=xtal if xtal is not None else _default_xtal(),
        image=image,
        load_hw=load_hw,
        extra_args=extra_args,
        session_id=session_id,
    )
    eng = _sessions.get(sid)
    return {
        "session_id": sid,
        "binary": eng.binary,
        "cpu": eng.cpu,
        "xtal": eng.xtal,
        "image": eng.image,
        "banner": eng.banner.strip(),
        "load_output": eng.load_output.strip(),
        "hw_modules": [
            {"path": m["path"], "id_string": m["id_string"], "ok": m["ok"]}
            for m in eng.hw_modules
        ],
    }


@mcp.tool
def list_sessions() -> list[dict]:
    """List all active ucSim sessions and their configuration."""
    return _sessions.list_ids()


@mcp.tool
def stop_session(session_id: str) -> dict:
    """Stop a ucSim session and terminate its simulator process."""
    _sessions.close(session_id)
    return {"session_id": session_id, "stopped": True}


# -- program loading & execution ----------------------------------------------
@mcp.tool
def load_image(session_id: str, image: str) -> dict:
    """Load a firmware image into a running session.

    ``@`` in the path is handled automatically (copied to a safe temp path).
    """
    eng = _sessions.get(session_id)
    return {"session_id": session_id, "output": eng.load(image)}


@mcp.tool
def reset(session_id: str) -> dict:
    """Reset the simulated CPU (equivalent to the ucSim ``reset`` command)."""
    eng = _sessions.get(session_id)
    return {"session_id": session_id, "output": eng.reset()}


@mcp.tool
def step(session_id: str, count: int = 1, timeout: float = 30.0) -> dict:
    """Advance the CPU by a bounded number of instructions (ucSim ``step N``).

    Prefer this over `run` when you want deterministic, bounded advance — on
    the MCS-51 build ``run N`` free-runs until a breakpoint and ignores N.
    """
    eng = _sessions.get(session_id)
    return {
        "session_id": session_id,
        "output": eng.step(count, timeout=timeout),
    }


@mcp.tool
def run(session_id: str, timeout: float = 30.0) -> dict:
    """Free-run the CPU until a breakpoint, stop condition, or the timeout.

    If the timeout elapses while still running, the simulation is interrupted
    (SIGINT) and the partial output is returned.
    """
    eng = _sessions.get(session_id)
    try:
        out = eng.run(timeout=timeout)
    except UCSimError:
        raise
    return {"session_id": session_id, "output": out}


@mcp.tool
def stop_run(session_id: str) -> dict:
    """Interrupt a free-running simulation (sends SIGINT to the process)."""
    eng = _sessions.get(session_id)
    eng.stop()
    return {"session_id": session_id, "interrupted": True}


# -- state inspection ---------------------------------------------------------
@mcp.tool
def get_state(session_id: str) -> dict:
    """Return the CPU state summary (ucSim ``state`` command: PC, cycles…)."""
    eng = _sessions.get(session_id)
    return {"session_id": session_id, "output": eng.command("state")}


@mcp.tool
def get_registers(session_id: str) -> dict:
    """Dump the CPU registers (ucSim ``info registers`` / ``reg``)."""
    eng = _sessions.get(session_id)
    out = eng.command("info registers")
    if "Undefined" in out or not out.strip():
        out = eng.command("reg")
    return {"session_id": session_id, "output": out}


@mcp.tool
def read_memory(
    session_id: str, space: str, start: int, end: int | None = None
) -> dict:
    """Dump memory (ucSim ``dump <space> <start> <end>``).

    Args:
        space: Memory space name, e.g. ``rom``/``code``, ``iram``, ``xram``,
            ``sfr`` (names depend on the simulated CPU).
        start: Start address.
        end: End address (inclusive). Defaults to ``start`` (single byte).
    """
    eng = _sessions.get(session_id)
    if end is None:
        end = start
    out = eng.command(f"dump {space} 0x{start:x} 0x{end:x}")
    return {"session_id": session_id, "output": out}


@mcp.tool
def write_memory(session_id: str, space: str, address: int, value: int) -> dict:
    """Write one byte to memory (ucSim ``set mem <space> <addr> <value>``)."""
    eng = _sessions.get(session_id)
    out = eng.command(
        f"set mem {space} 0x{address:x} 0x{value & 0xFF:x}")
    return {"session_id": session_id, "output": out}


@mcp.tool
def disassemble(
    session_id: str, start: int | None = None, end: int | None = None
) -> dict:
    """Disassemble a range of code (ucSim ``dc [start [stop]]``).

    Args:
        start: Start address. If omitted, disassembles from the current PC.
        end: Stop address (inclusive-ish; ucSim decodes up to it). If omitted,
            ucSim disassembles a short default span from ``start``.

    Note: this ucSim build uses ``dc`` (dump code, disassembled form); the old
    ``disassemble`` command was removed. ``dch`` is the hex-only variant.
    """
    eng = _sessions.get(session_id)
    parts = ["dc"]
    if start is not None:
        parts.append(f"0x{start:x}")
        if end is not None:
            parts.append(f"0x{end:x}")
    return {"session_id": session_id, "output": eng.command(" ".join(parts))}


# -- breakpoints --------------------------------------------------------------
@mcp.tool
def set_breakpoint(session_id: str, address: int) -> dict:
    """Set an execution breakpoint (ucSim ``break 0x<addr>``)."""
    eng = _sessions.get(session_id)
    out = eng.command(f"break 0x{address:x}")
    return {"session_id": session_id, "output": out}


@mcp.tool
def clear_breakpoint(session_id: str, address: int) -> dict:
    """Clear an execution breakpoint (ucSim ``clear 0x<addr>``)."""
    eng = _sessions.get(session_id)
    out = eng.command(f"clear 0x{address:x}")
    return {"session_id": session_id, "output": out}


@mcp.tool
def list_breakpoints(session_id: str) -> dict:
    """List all breakpoints (ucSim ``info breakpoints``)."""
    eng = _sessions.get(session_id)
    return {"session_id": session_id, "output": eng.command("info breakpoints")}


# -- peripherals & escape hatch -----------------------------------------------
@mcp.tool
def load_hardware(session_id: str, so_path: str) -> dict:
    """Load a cl_hw plugin shared object (ucSim ``loadhw "FILE.so"``).

    The plugin must be built against the ucsim-plugin-sdk for the *same* ucSim
    binary (the C++ ABI must match). After loading, drive it with
    `set_hardware` using the returned ``id_string`` as the first token
    (e.g. ``set_hardware(sid, "adc 0 0x80")``).

    Note on load order: a module loaded at runtime registers *after* the core
    hardware, so if it must observe the very first instruction fetch, pass it
    via `start_session(load_hw=[...])` instead (which loads before image/reset).

    Returns:
        The resolved path, the parsed ``id_string``, whether the load
        succeeded, and the raw ucSim output.
    """
    eng = _sessions.get(session_id)
    info = eng.load_hw(so_path)
    return {"session_id": session_id, **info}


@mcp.tool
def list_hardware(session_id: str) -> dict:
    """List hardware: loaded cl_hw plugins plus ucSim's own ``info hardware``.

    Returns the plugins loaded in this session (path + ``id_string``) and the
    simulator's live hardware listing.
    """
    eng = _sessions.get(session_id)
    info = eng.command("info hardware")
    if "Undefined" in info or not info.strip():
        info = eng.command("set hardware")  # falls back to the hw summary
    return {
        "session_id": session_id,
        "plugins": [
            {"path": m["path"], "id_string": m["id_string"], "ok": m["ok"]}
            for m in eng.hw_modules
        ],
        "output": info,
    }


@mcp.tool
def set_hardware(session_id: str, args: str) -> dict:
    """Drive a peripheral (ucSim ``set hardware <args>``).

    Example: ``set_hardware(sid, "adc 0 0x80")`` or a loaded cl_hw plugin.
    """
    eng = _sessions.get(session_id)
    out = eng.command(f"set hardware {args}")
    return {"session_id": session_id, "output": out}


@mcp.tool
def ucsim_command(session_id: str, command: str, timeout: float = 10.0) -> dict:
    """Run an arbitrary raw ucSim console command and return its output.

    Escape hatch for anything not covered by a dedicated tool. Do NOT pipeline
    multiple commands or embed a ``run``/``step`` here together with another
    command — send one command per call.
    """
    eng = _sessions.get(session_id)
    return {
        "session_id": session_id,
        "output": eng.command(command, timeout=timeout),
    }


def main() -> None:
    try:
        mcp.run()
    finally:
        _sessions.close_all()


if __name__ == "__main__":
    main()
