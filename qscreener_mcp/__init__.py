"""Standalone qscreener MCP server.

Exposes the qscreener screener operations as MCP tools over either stdio (local
agent subprocess) or streamable-HTTP (remote, externally reachable). Tools call
the stobot backend API directly over HTTP; the server has no dependency on the
``stobot`` Python package. See :mod:`qscreener_mcp.server`.
"""
