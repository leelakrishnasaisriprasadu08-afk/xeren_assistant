"""Abstract Syntax Tree (AST) parser and multi-symbol code extractor."""

import ast
from enum import Enum
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Set
from pydantic import BaseModel, Field


class SymbolType(str, Enum):
  CLASS = "CLASS"
  FUNCTION = "FUNCTION"
  ASYNC_FUNCTION = "ASYNC_FUNCTION"
  METHOD = "METHOD"
  IMPORT = "IMPORT"
  GLOBAL_VARIABLE = "GLOBAL_VARIABLE"
  ENDPOINT = "ENDPOINT"


class SymbolNode(BaseModel):
  """Representation of an extracted code symbol."""

  name: str
  qualified_name: str
  symbol_type: SymbolType
  file_path: str
  line_start: int
  line_end: int
  docstring: Optional[str] = None
  signature: Optional[str] = None
  return_type: Optional[str] = None
  decorators: List[str] = Field(default_factory=list)
  callees: List[str] = Field(default_factory=list)
  is_async: bool = False


class _PythonASTVisitor(ast.NodeVisitor):
  """Internal AST visitor extracting structural symbols and call relations."""

  def __init__(self, file_path: str, source_code: str):
    self.file_path = file_path
    self.source_lines = source_code.splitlines()
    self.symbols: List[SymbolNode] = []
    self.current_class: Optional[str] = None
    self.current_callable: Optional[str] = None
    self.imports: List[str] = []

  def _get_decorator_names(self, decorator_list: List[ast.expr]) -> List[str]:
    names = []
    for d in decorator_list:
      if isinstance(d, ast.Name):
        names.append(d.id)
      elif isinstance(d, ast.Attribute):
        names.append(f"{ast.unparse(d)}")
      elif isinstance(d, ast.Call):
        names.append(ast.unparse(d.func))
    return names

  def _extract_signature(
      self, node: ast.FunctionDef | ast.AsyncFunctionDef
  ) -> str:
    try:
      args_list = []
      for arg in node.args.args:
        ann = f": {ast.unparse(arg.annotation)}" if arg.annotation else ""
        args_list.append(f"{arg.arg}{ann}")
      if node.args.vararg:
        args_list.append(f"*{node.args.vararg.arg}")
      if node.args.kwarg:
        args_list.append(f"**{node.args.kwarg.arg}")
      return f"({', '.join(args_list)})"
    except Exception:
      return "()"

  def visit_ClassDef(self, node: ast.ClassDef):
    prev_class = self.current_class
    self.current_class = node.name
    doc = ast.get_docstring(node)
    decorators = self._get_decorator_names(node.decorator_list)

    symbol = SymbolNode(
        name=node.name,
        qualified_name=node.name,
        symbol_type=SymbolType.CLASS,
        file_path=self.file_path,
        line_start=node.lineno,
        line_end=getattr(node, "end_lineno", node.lineno),
        docstring=doc,
        decorators=decorators,
    )
    self.symbols.append(symbol)

    # Continue traversing class body
    self.generic_visit(node)
    self.current_class = prev_class

  def _visit_function(
      self, node: ast.FunctionDef | ast.AsyncFunctionDef, is_async: bool
  ):
    prev_callable = self.current_callable
    if self.current_class:
      qname = f"{self.current_class}.{node.name}"
      stype = SymbolType.METHOD
    else:
      qname = node.name
      stype = SymbolType.ASYNC_FUNCTION if is_async else SymbolType.FUNCTION

    doc = ast.get_docstring(node)
    decorators = self._get_decorator_names(node.decorator_list)
    sig = self._extract_signature(node)
    ret = ast.unparse(node.returns) if node.returns else None

    # Detect FastAPI or Flask route decorators
    if any(
        dec.endswith((".get", ".post", ".put", ".delete", ".patch"))
        or "app." in dec
        or "router." in dec
        for dec in decorators
    ):
      stype = SymbolType.ENDPOINT

    symbol = SymbolNode(
        name=node.name,
        qualified_name=qname,
        symbol_type=stype,
        file_path=self.file_path,
        line_start=node.lineno,
        line_end=getattr(node, "end_lineno", node.lineno),
        docstring=doc,
        signature=sig,
        return_type=ret,
        decorators=decorators,
        is_async=is_async,
    )
    self.symbols.append(symbol)
    self.current_callable = qname

    # Traverse function body to detect calls
    self.generic_visit(node)
    self.current_callable = prev_callable

  def visit_FunctionDef(self, node: ast.FunctionDef):
    self._visit_function(node, is_async=False)

  def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
    self._visit_function(node, is_async=True)

  def visit_Call(self, node: ast.Call):
    if self.current_callable:
      try:
        callee_name = ast.unparse(node.func)
        # Find matching current callable symbol
        for sym in self.symbols:
          if sym.qualified_name == self.current_callable:
            if callee_name not in sym.callees:
              sym.callees.append(callee_name)
            break
      except Exception:
        pass
    self.generic_visit(node)

  def visit_Import(self, node: ast.Import):
    for alias in node.names:
      self.imports.append(alias.name)
      self.symbols.append(
          SymbolNode(
              name=alias.name,
              qualified_name=alias.name,
              symbol_type=SymbolType.IMPORT,
              file_path=self.file_path,
              line_start=node.lineno,
              line_end=getattr(node, "end_lineno", node.lineno),
          )
      )

  def visit_ImportFrom(self, node: ast.ImportFrom):
    mod = node.module or ""
    for alias in node.names:
      full_name = f"{mod}.{alias.name}" if mod else alias.name
      self.imports.append(full_name)
      self.symbols.append(
          SymbolNode(
              name=alias.name,
              qualified_name=full_name,
              symbol_type=SymbolType.IMPORT,
              file_path=self.file_path,
              line_start=node.lineno,
              line_end=getattr(node, "end_lineno", node.lineno),
          )
      )

  def visit_Assign(self, node: ast.Assign):
    # Only top-level assignments
    if self.current_class is None and self.current_callable is None:
      for target in node.targets:
        if isinstance(target, ast.Name) and target.id.isupper():
          self.symbols.append(
              SymbolNode(
                  name=target.id,
                  qualified_name=target.id,
                  symbol_type=SymbolType.GLOBAL_VARIABLE,
                  file_path=self.file_path,
                  line_start=node.lineno,
                  line_end=getattr(node, "end_lineno", node.lineno),
              )
          )
    self.generic_visit(node)


class ASTParser:
  """Main parser extracting code symbols and metadata from workspace source files."""

  @staticmethod
  def parse_python_file(file_path: str, content: str) -> List[SymbolNode]:
    """Parses a Python source file using AST and returns structured symbols."""
    if not content or not content.strip():
      return []

    try:
      tree = ast.parse(content, filename=file_path)
      visitor = _PythonASTVisitor(file_path=file_path, source_code=content)
      visitor.visit(tree)
      return visitor.symbols
    except SyntaxError:
      # Fallback to regex symbol extraction for partially malformed code
      return ASTParser._regex_fallback_parse(file_path, content)

  @staticmethod
  def _regex_fallback_parse(file_path: str, content: str) -> List[SymbolNode]:
    symbols = []
    lines = content.splitlines()

    class_pat = re.compile(r"^\s*class\s+([A-Za-z0-9_]+)")
    func_pat = re.compile(r"^\s*(async\s+)?def\s+([A-Za-z0-9_]+)\s*\((.*?)\)")

    for idx, line in enumerate(lines, start=1):
      cmatch = class_pat.match(line)
      if cmatch:
        symbols.append(
            SymbolNode(
                name=cmatch.group(1),
                qualified_name=cmatch.group(1),
                symbol_type=SymbolType.CLASS,
                file_path=file_path,
                line_start=idx,
                line_end=idx,
            )
        )
        continue

      fmatch = func_pat.match(line)
      if fmatch:
        is_async = bool(fmatch.group(1))
        fname = fmatch.group(2)
        symbols.append(
            SymbolNode(
                name=fname,
                qualified_name=fname,
                symbol_type=(
                    SymbolType.ASYNC_FUNCTION if is_async else SymbolType.FUNCTION
                ),
                file_path=file_path,
                line_start=idx,
                line_end=idx,
                is_async=is_async,
            )
        )

    return symbols

  @classmethod
  def parse_file(cls, file_path: str | Path, content: str) -> List[SymbolNode]:
    """Universal file parser routing by extension."""
    path_str = str(file_path)
    if path_str.endswith(".py"):
      return cls.parse_python_file(path_str, content)
    # Generic token fallback
    return cls._regex_fallback_parse(path_str, content)
