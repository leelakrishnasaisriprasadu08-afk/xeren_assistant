"""Persistent SQLite codebase symbol indexer and incremental workspace scanner."""

import hashlib
import json
from pathlib import Path
import sqlite3
import time
from typing import Any, Dict, List, Optional
from .ast_parser import ASTParser, SymbolNode, SymbolType
from .graph import CodeGraph


class CodebaseIndexer:
  """Indexes workspace source files, populating SQLite tables and in-memory CodeGraph."""

  IGNORED_DIRS = {
      ".git",
      ".venv",
      "venv",
      "__pycache__",
      ".pytest_cache",
      "traces",
      "data",
      ".vscode",
      ".idea",
      "htmlcov",
      "build",
      "dist",
  }

  def __init__(
      self,
      workspace_root: Optional[Path] = None,
      db_path: Optional[Path] = None,
  ):
    self.workspace_root = (workspace_root or Path(".")).resolve()
    self.db_path = (db_path or Path("data/xeren.sqlite")).resolve()
    self.db_path.parent.mkdir(parents=True, exist_ok=True)
    self.graph = CodeGraph()
    self._init_db()

  def _get_connection(self) -> sqlite3.Connection:
    conn = sqlite3.connect(str(self.db_path))
    conn.row_factory = sqlite3.Row
    return conn

  def _init_db(self) -> None:
    with self._get_connection() as conn:
      conn.executescript("""
                CREATE TABLE IF NOT EXISTS codebase_files (
                    file_path TEXT PRIMARY KEY,
                    file_hash TEXT NOT NULL,
                    last_indexed REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS codebase_symbols (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    qualified_name TEXT NOT NULL,
                    symbol_type TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    line_start INTEGER NOT NULL,
                    line_end INTEGER NOT NULL,
                    signature TEXT,
                    docstring TEXT,
                    decorators TEXT,
                    callees TEXT,
                    is_async INTEGER DEFAULT 0
                );

                CREATE INDEX IF NOT EXISTS idx_sym_name ON codebase_symbols(name);
                CREATE INDEX IF NOT EXISTS idx_sym_qname ON codebase_symbols(qualified_name);
                CREATE INDEX IF NOT EXISTS idx_sym_file ON codebase_symbols(file_path);
                CREATE INDEX IF NOT EXISTS idx_sym_type ON codebase_symbols(symbol_type);
            """)
      conn.commit()

  def _compute_file_hash(self, path: Path) -> str:
    try:
      return hashlib.sha256(path.read_bytes()).hexdigest()
    except Exception:
      return ""

  def index_workspace(self, force: bool = False) -> Dict[str, Any]:
    """Scans and indexes all supported source files in workspace_root."""
    start_time = time.perf_counter()
    files_scanned = 0
    files_updated = 0
    total_symbols = 0

    self.graph.clear()
    all_symbols: List[SymbolNode] = []

    with self._get_connection() as conn:
      # Fetch existing file hashes
      existing_hashes = {
          row["file_path"]: row["file_hash"]
          for row in conn.execute(
              "SELECT file_path, file_hash FROM codebase_files"
          ).fetchall()
      }

      for path in self.workspace_root.rglob("*.py"):
        if any(part in self.IGNORED_DIRS for part in path.parts):
          continue

        rel_path = str(path.relative_to(self.workspace_root)).replace("\\", "/")
        files_scanned += 1
        current_hash = self._compute_file_hash(path)

        needs_reindex = (
            force
            or rel_path not in existing_hashes
            or existing_hashes[rel_path] != current_hash
        )

        try:
          content = path.read_text(encoding="utf-8", errors="replace")
          symbols = ASTParser.parse_file(rel_path, content)
          all_symbols.extend(symbols)

          if needs_reindex:
            files_updated += 1
            # Delete old symbols for this file
            conn.execute(
                "DELETE FROM codebase_symbols WHERE file_path = ?", (rel_path,)
            )

            # Insert new symbols
            for sym in symbols:
              conn.execute(
                  """
                                INSERT INTO codebase_symbols (
                                    name, qualified_name, symbol_type, file_path,
                                    line_start, line_end, signature, docstring,
                                    decorators, callees, is_async
                                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                  (
                      sym.name,
                      sym.qualified_name,
                      sym.symbol_type.value,
                      sym.file_path,
                      sym.line_start,
                      sym.line_end,
                      sym.signature,
                      sym.docstring,
                      json.dumps(sym.decorators),
                      json.dumps(sym.callees),
                      1 if sym.is_async else 0,
                  ),
              )

            conn.execute(
                """
                            INSERT OR REPLACE INTO codebase_files (file_path, file_hash, last_indexed)
                            VALUES (?, ?, ?)
                        """,
                (rel_path, current_hash, time.time()),
            )
        except Exception:
          continue

      conn.commit()

    self.graph.add_symbols(all_symbols)
    total_symbols = len(all_symbols)
    elapsed_ms = (time.perf_counter() - start_time) * 1000

    return {
        "files_scanned": files_scanned,
        "files_updated": files_updated,
        "total_symbols_indexed": total_symbols,
        "elapsed_ms": elapsed_ms,
    }

  def search_symbols(
      self,
      query: str,
      symbol_type: Optional[str] = None,
      file_pattern: Optional[str] = None,
      limit: int = 25,
  ) -> List[Dict[str, Any]]:
    """Searches indexed symbols matching query name or qualified name."""
    sql = """
            SELECT name, qualified_name, symbol_type, file_path, line_start, line_end,
                   signature, docstring, decorators, callees, is_async
            FROM codebase_symbols
            WHERE (name LIKE ? OR qualified_name LIKE ? OR docstring LIKE ?)
        """
    params = [f"%{query}%", f"%{query}%", f"%{query}%"]

    if symbol_type:
      sql += " AND symbol_type = ?"
      params.append(symbol_type.upper())

    if file_pattern:
      sql += " AND file_path LIKE ?"
      params.append(f"%{file_pattern}%")

    sql += " ORDER BY CASE WHEN name = ? THEN 1 WHEN name LIKE ? THEN 2 ELSE 3 END LIMIT ?"
    params.extend([query, f"{query}%", limit])

    results = []
    with self._get_connection() as conn:
      for row in conn.execute(sql, params).fetchall():
        results.append({
            "name": row["name"],
            "qualified_name": row["qualified_name"],
            "type": row["symbol_type"],
            "file_path": row["file_path"],
            "line_start": row["line_start"],
            "line_end": row["line_end"],
            "signature": row["signature"],
            "docstring": row["docstring"],
            "decorators": (
                json.loads(row["decorators"]) if row["decorators"] else []
            ),
            "callees": json.loads(row["callees"]) if row["callees"] else [],
            "is_async": bool(row["is_async"]),
        })

    return results

  def get_file_outline(self, file_path: str) -> List[Dict[str, Any]]:
    """Fetches outline for a file from DB or in-memory graph."""
    outline = self.graph.get_file_outline(file_path)
    if outline:
      return outline

    # DB fallback if not in graph
    clean_path = file_path.replace("\\", "/")
    results = []
    with self._get_connection() as conn:
      rows = conn.execute(
          """
                SELECT name, qualified_name, symbol_type, line_start, line_end,
                       signature, docstring, decorators, is_async
                FROM codebase_symbols
                WHERE file_path = ? AND symbol_type != 'IMPORT'
                ORDER BY line_start ASC
            """,
          (clean_path,),
      ).fetchall()

      for row in rows:
        results.append({
            "name": row["name"],
            "qualified_name": row["qualified_name"],
            "type": row["symbol_type"],
            "line_start": row["line_start"],
            "line_end": row["line_end"],
            "signature": row["signature"],
            "docstring": row["docstring"],
            "decorators": (
                json.loads(row["decorators"]) if row["decorators"] else []
            ),
            "is_async": bool(row["is_async"]),
        })
    return results

  def get_call_hierarchy(self, symbol_name: str) -> Dict[str, Any]:
    """Returns caller and callee hierarchies for a target symbol."""
    sym = self.graph.find_symbol(symbol_name)
    callers = self.graph.find_callers(symbol_name)
    callees = (
        self.graph.find_callees(symbol_name)
        if not sym
        else self.graph.find_callees(sym.qualified_name)
    )

    return {
        "symbol": sym.model_dump() if sym else {"name": symbol_name},
        "callers": [c.model_dump() for c in callers],
        "callees": callees,
    }
