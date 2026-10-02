"""Tests for the ucsim-mcp server tools, exercised through a FastMCP client.

Engine-level behaviour (pty I/O, @-filename handling, step vs run, cl_hw
loading) is covered in the pyucsim library's own test suite; here we verify the
MCP tool layer wires correctly to it.
"""
import pytest
from fastmcp import Client

from ucsim_mcp.server import mcp

from conftest import ROB3_ROM, requires_binary, requires_rom


@pytest.mark.asyncio
async def test_tools_are_registered():
    tools = {t.name for t in await mcp.list_tools()}
    expected = {
        "start_session", "list_sessions", "stop_session", "load_image",
        "reset", "step", "run", "stop_run", "get_state", "get_registers",
        "read_memory", "write_memory", "disassemble", "set_breakpoint",
        "clear_breakpoint", "list_breakpoints", "load_hardware",
        "list_hardware", "set_hardware", "ucsim_command",
    }
    assert expected <= tools


@pytest.mark.asyncio
async def test_list_sessions_empty():
    async with Client(mcp) as c:
        res = await c.call_tool("list_sessions", {})
        assert res.data == []


@requires_binary
@requires_rom
@pytest.mark.asyncio
async def test_full_session_flow():
    async with Client(mcp) as c:
        s = (await c.call_tool("start_session", {"image": ROB3_ROM})).data
        sid = s["session_id"]
        try:
            # reset vector LJMP 0x0600
            rv = (await c.call_tool("read_memory", {
                "session_id": sid, "space": "rom", "start": 0, "end": 2,
            })).data["output"]
            assert "02 06 00" in rv

            await c.call_tool("reset", {"session_id": sid})
            st = (await c.call_tool("step", {
                "session_id": sid, "count": 10})).data["output"]
            assert "stepped" in st.lower()

            await c.call_tool("write_memory", {
                "session_id": sid, "space": "iram",
                "address": 0x50, "value": 0x42})
            rd = (await c.call_tool("read_memory", {
                "session_id": sid, "space": "iram",
                "start": 0x50, "end": 0x50})).data["output"]
            assert "42" in rd

            dis = (await c.call_tool("disassemble", {
                "session_id": sid, "start": 0x600, "end": 0x604})).data["output"]
            assert "MOV" in dis.upper()
            assert "Removed command" not in dis
        finally:
            stop = (await c.call_tool(
                "stop_session", {"session_id": sid})).data
            assert stop["stopped"]
