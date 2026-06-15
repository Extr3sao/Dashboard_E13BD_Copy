import asyncio
import sqlite3
import os
from mcp.server.fastapi import Context
from mcp.server import Server
import mcp.types as types

# Servidor MCP per a la base de dades interna
app = Server("oracle-audit-knowledge")

DB_PATH = "src/db/internal.db"

@app.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="query_knowledge",
            description="Consulta el repositori de coneixement de consultes SQL expertes.",
            inputSchema={
                "type": "object",
                "properties": {
                    "search_term": {"type": "string", "description": "Terme de cerca (ex: 'obsolets', 'espai')"},
                },
            },
        ),
        types.Tool(
            name="add_expert_query",
            description="Afegeix una nova consulta experta al hub de coneixement.",
            inputSchema={
                "type": "object",
                "properties": {
                    "sql": {"type": "string"},
                    "explanation": {"type": "string"},
                    "tags": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["sql", "explanation"],
            },
        )
    ]

@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    if name == "query_knowledge":
        search = arguments.get("search_term", "")
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT sql_text, explanation FROM queries WHERE sql_text LIKE ? OR explanation LIKE ?", 
                           (f"%{search}%", f"%{search}%"))
            results = cursor.fetchall()
            if not results:
                return [types.TextContent(type="text", text="No s'han trobat resultats.")]
            
            output = "\n---\n".join([f"SQL: {r[0]}\nExplicació: {r[1]}" for r in results])
            return [types.TextContent(type="text", text=output)]

    elif name == "add_expert_query":
        sql = arguments["sql"]
        explanation = arguments["explanation"]
        tags = arguments.get("tags", [])
        # Crida al mètode d'InternalDBManager (simulat per simplificar el servidor MCP)
        from src.core.internal_db import InternalDBManager
        db = InternalDBManager(DB_PATH)
        db.add_query(sql, explanation, source="MCP", tags=tags)
        return [types.TextContent(type="text", text="Consulta afegida correctament via MCP.")]

if __name__ == "__main__":
    from mcp.server.stdio import stdio_server
    asyncio.run(stdio_server(app))
