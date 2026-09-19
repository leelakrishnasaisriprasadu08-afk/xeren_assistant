"""Unit tests for CodeGraph hierarchy and call graph modeling."""

import pytest
from codebase.ast_parser import SymbolNode, SymbolType
from codebase.graph import CodeGraph


def test_code_graph_callers_and_callees():
  graph = CodeGraph()

  sym_a = SymbolNode(
      name="service_a",
      qualified_name="pkg.service_a",
      symbol_type=SymbolType.FUNCTION,
      file_path="pkg/a.py",
      line_start=1,
      line_end=10,
      callees=["service_b", "service_c"],
  )
  sym_b = SymbolNode(
      name="service_b",
      qualified_name="pkg.service_b",
      symbol_type=SymbolType.FUNCTION,
      file_path="pkg/b.py",
      line_start=1,
      line_end=5,
      callees=[],
  )

  graph.add_symbols([sym_a, sym_b])

  # Check find_symbol
  found = graph.find_symbol("service_a")
  assert found is not None
  assert found.qualified_name == "pkg.service_a"

  # Check callers of service_b
  callers = graph.find_callers("service_b")
  assert len(callers) == 1
  assert callers[0].qualified_name == "pkg.service_a"

  # Check callees of service_a
  callees = graph.find_callees("pkg.service_a")
  assert "service_b" in callees
  assert "service_c" in callees


def test_code_graph_outline_and_dependencies():
  graph = CodeGraph()

  sym1 = SymbolNode(
      name="MyClass",
      qualified_name="MyClass",
      symbol_type=SymbolType.CLASS,
      file_path="module.py",
      line_start=5,
      line_end=20,
  )
  sym_imp = SymbolNode(
      name="os",
      qualified_name="os",
      symbol_type=SymbolType.IMPORT,
      file_path="module.py",
      line_start=1,
      line_end=1,
  )

  graph.add_symbols([sym1, sym_imp])

  outline = graph.get_file_outline("module.py")
  assert len(outline) == 1
  assert outline[0]["name"] == "MyClass"

  deps = graph.get_file_dependencies("module.py")
  assert "os" in deps
