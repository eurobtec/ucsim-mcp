"""ucsim-mcp: a Model Context Protocol server for the µCsim simulator.

Exposes a persistent ucSim process (``ucsim_51`` / ``s51`` and the other
``ucsim_*`` family binaries) to MCP clients so that an AI model can load a
firmware image, reset/run/step the CPU, inspect and modify memory and
registers, set breakpoints, and drive peripherals — all over the normal MCP
tool interface.
"""

__version__ = "0.1.0"
