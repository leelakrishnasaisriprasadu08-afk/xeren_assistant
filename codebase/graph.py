"""In-memory CodeGraph representing symbol hierarchies and caller/callee relations."""

from collections import defaultdict
from typing import Any, Dict, List, Optional, Set
from .ast_parser import SymbolNode, SymbolType


class CodeGraph:
  """Directed graph mapping code symbols, calls, and file-level dependencies."""

  def __init__(self):
    self.symbols_by_qname: Dict[str, SymbolNode] = {}
    self.symbols_by_file: Dict[str, List[SymbolNode]] = defaultdict(list)
    self.callers_map: Dict[str, Set[str]] = defaultdict(set)  # callee -> callers
    self.callees_map: Dict[str, Set[str]] = defaultdict(set)  # caller -> callees
    self.file_imports: Dict[str, Set[str]] = defaultdict(set)

  def add_symbol(self, symbol: SymbolNode) -> None:
    """Adds a single SymbolNode to the graph and updates edge indices."""
    self.symbols_by_qname[symbol.qualified_name] = symbol
    self.symbols_by_file[symbol.file_path].append(symbol)

    if symbol.symbol_type == SymbolType.IMPORT:
      self.file_imports[symbol.file_path].add(symbol.name)

    # Index call relationships
    for callee in symbol.callees:
      # Strip self or module qualification for fuzzy matching
      base_callee = callee.split(".")[-1]
      self.callees_map[symbol.qualified_name].add(callee)
      self.callers_map[callee].add(symbol.qualified_name)
      if base_callee != callee:
        self.callers_map[base_callee].add(symbol.qualified_name)

  def add_symbols(self, symbols: List[SymbolNode]) -> None:
    """Bulk adds a list of symbols into the code graph."""
    for sym in symbols:
      self.add_symbol(sym)

  def find_symbol(self, name: str) -> Optional[SymbolNode]:
    """Finds a symbol by qualified name or short name."""
    if name in self.symbols_by_qname:
      return self.symbols_by_qname[name]
    for sym in self.symbols_by_qname.values():
      if sym.name == name:
        return sym
    return None

  def find_callers(self, target_name: str) -> List[SymbolNode]:
    """Finds all symbol nodes that call target_name."""
    caller_qnames = self.callers_map.get(target_name, set())
    # Also check base name if qualified
    base_name = target_name.split(".")[-1]
    if base_name in self.callers_map:
      caller_qnames = caller_qnames.union(self.callers_map[base_name])

    results = []
    for qname in caller_qnames:
      if qname in self.symbols_by_qname:
        results.append(self.symbols_by_qname[qname])
    return results

  def find_callees(self, caller_name: str) -> List[str]:
    """Finds all callee names invoked by caller_name."""
    return list(self.callees_map.get(caller_name, set()))

  def get_file_outline(self, file_path: str) -> List[Dict[str, Any]]:
    """Generates a hierarchical structural outline for a file."""
    symbols = self.symbols_by_file.get(file_path, [])
    # Sort by starting line number
    sorted_symbols = sorted(symbols, key=lambda s: s.line_start)
    outline = []
    for sym in sorted_symbols:
      if sym.symbol_type == SymbolType.IMPORT:
        continue
      outline.append({
          "name": sym.name,
          "qualified_name": sym.qualified_name,
          "type": sym.symbol_type.value,
          "line_start": sym.line_start,
          "line_end": sym.line_end,
          "signature": sym.signature,
          "docstring": sym.docstring,
          "decorators": sym.decorators,
          "is_async": sym.is_async,
      })
    return outline

  def get_file_dependencies(self, file_path: str) -> List[str]:
    """Returns all external imports and referenced modules for a file."""
    return sorted(list(self.file_imports.get(file_path, set())))

  def clear(self) -> None:
    """Resets the graph."""
    self.symbols_by_qname.clear()
    self.symbols_by_file.clear()
    self.callers_map.clear()
    self.callees_map.clear()
    self.file_imports.clear()
