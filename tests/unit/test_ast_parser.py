"""Unit tests for AST Parser and symbol extraction."""

import pytest
from codebase.ast_parser import ASTParser, SymbolNode, SymbolType


def test_ast_parser_extracts_classes_functions_methods():
  source = """
import os
from pathlib import Path

GLOBAL_CONST = "XEREN"

class SampleService:
    \"\"\"Sample service class docstring.\"\"\"
    
    def __init__(self, name: str):
        self.name = name

    def compute(self, x: int, y: int = 10) -> int:
        \"\"\"Computes sum.\"\"\"
        return self._internal_helper(x, y)

    def _internal_helper(self, a: int, b: int) -> int:
        return a + b

async def async_fetch_data(url: str) -> dict:
    \"\"\"Fetches remote payload.\"\"\"
    return {"status": "ok"}
"""
  symbols = ASTParser.parse_python_file("sample.py", source)
  assert len(symbols) >= 6

  # Check Class
  classes = [s for s in symbols if s.symbol_type == SymbolType.CLASS]
  assert len(classes) == 1
  assert classes[0].name == "SampleService"
  assert "Sample service class docstring" in (classes[0].docstring or "")

  # Check Methods
  methods = [s for s in symbols if s.symbol_type == SymbolType.METHOD]
  method_names = [m.name for m in methods]
  assert "__init__" in method_names
  assert "compute" in method_names
  assert "_internal_helper" in method_names

  # Check Async Function
  async_funcs = [
      s for s in symbols if s.symbol_type == SymbolType.ASYNC_FUNCTION
  ]
  assert len(async_funcs) == 1
  assert async_funcs[0].name == "async_fetch_data"
  assert async_funcs[0].is_async is True

  # Check Global Constant
  globals_list = [
      s for s in symbols if s.symbol_type == SymbolType.GLOBAL_VARIABLE
  ]
  assert len(globals_list) == 1
  assert globals_list[0].name == "GLOBAL_CONST"


def test_ast_parser_extracts_callees():
  source = """
def alpha():
    beta()
    gamma()

def beta():
    pass

def gamma():
    pass
"""
  symbols = ASTParser.parse_python_file("call_test.py", source)
  alpha_sym = next(s for s in symbols if s.name == "alpha")
  assert "beta" in alpha_sym.callees
  assert "gamma" in alpha_sym.callees
