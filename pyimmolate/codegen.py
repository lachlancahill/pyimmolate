"""Python → OpenCL C transpiler.

Walks the AST of a `@filter` (and its `@helper`s) and emits a complete `.cl`
file ready for Immolate to compile. Handles:

  * variable declarations with type inference from API return types
  * `item_array(n)` / `int_array(n[, init])` array declarations
  * `inst` field access (snake_case → camelCase via _inst.PARAMS_FIELD_MAP)
  * automatic `inst` injection at every API call site
  * helpers, including `ref(x)` pass-by-reference parameters
  * `raw_helpers=` escape hatch
  * if / elif / else, while, range-based for, break, continue, return
  * Python operators → C equivalents (//, or, and, not, True, False)

The transpiler does NOT execute filter bodies as Python — it works purely on
the AST captured at decoration time.
"""

from __future__ import annotations

import ast
import textwrap
from dataclasses import dataclass, field
from typing import Any

from pyimmolate._api_signatures import API_SIGNATURES
from pyimmolate._core import FilterFunction, HelperFunction
from pyimmolate._inst import INST_FIELD_MAP, PARAMS_FIELD_MAP

# ──────────────────────────────────────────────────────────────────────────
# Operator translation
# ──────────────────────────────────────────────────────────────────────────

_BINOP = {
    ast.Add: "+", ast.Sub: "-", ast.Mult: "*", ast.Div: "/",
    ast.FloorDiv: "/",  # both operands are integers in our DSL
    ast.Mod: "%", ast.LShift: "<<", ast.RShift: ">>",
    ast.BitAnd: "&", ast.BitOr: "|", ast.BitXor: "^",
}
_CMPOP = {
    ast.Eq: "==", ast.NotEq: "!=",
    ast.Lt: "<", ast.LtE: "<=",
    ast.Gt: ">", ast.GtE: ">=",
}
_BOOLOP = {ast.And: "&&", ast.Or: "||"}
_UNARYOP = {ast.UAdd: "+", ast.USub: "-", ast.Not: "!", ast.Invert: "~"}
_AUGOP = {
    ast.Add: "+=", ast.Sub: "-=", ast.Mult: "*=", ast.Div: "/=",
    ast.FloorDiv: "/=", ast.Mod: "%=",
    ast.LShift: "<<=", ast.RShift: ">>=",
    ast.BitAnd: "&=", ast.BitOr: "|=", ast.BitXor: "^=",
}

# Map (struct C type) → fields and their C names. Used to type subsequent
# attribute access like `_pack.size` once `_pack` is known to be of type `pack`.
_STRUCT_FIELDS: dict[str, dict[str, tuple[str, str]]] = {
    # python_field_name -> (c_field_name, c_field_type)
    "pack": {
        "type": ("type", "item"),
        "size": ("size", "int"),
        "choices": ("choices", "int"),
    },
    "shopitem": {
        "type": ("type", "itemtype"),
        "value": ("value", "item"),
        "joker": ("joker", "jokerdata"),
    },
    "card": {
        "base": ("base", "item"),
        "edition": ("edition", "item"),
        "enhancement": ("enhancement", "item"),
        "seal": ("seal", "item"),
    },
    "jokerdata": {
        "joker": ("joker", "item"),
        "edition": ("edition", "item"),
        "stickers": ("stickers", "jokerstickers"),
    },
    "jokerstickers": {
        "eternal": ("eternal", "bool"),
        "perishable": ("perishable", "bool"),
        "rental": ("rental", "bool"),
    },
}


# ──────────────────────────────────────────────────────────────────────────
# Helper-call ref tracking
# ──────────────────────────────────────────────────────────────────────────


@dataclass
class HelperRefInfo:
    """Per-helper-param: did call sites pass it by ref()?"""
    by_ref: bool = False
    saw_value: bool = False  # observed at least one non-ref call
    saw_ref: bool = False    # observed at least one ref(...) call
    inferred_type: str = "int"  # C base type (without '*')


# ──────────────────────────────────────────────────────────────────────────
# Scope / type environment
# ──────────────────────────────────────────────────────────────────────────


@dataclass
class Scope:
    declared: dict[str, str] = field(default_factory=dict)
    """name → C type. Used to suppress redeclaration on reassignment and to
    resolve attribute access on struct-typed locals."""

    ref_params: set[str] = field(default_factory=set)
    """Names of params that are pointer-typed in this function (helper only)."""


# ──────────────────────────────────────────────────────────────────────────
# Transpiler
# ──────────────────────────────────────────────────────────────────────────


class Transpiler:
    def __init__(self, filt: FilterFunction) -> None:
        self.filt = filt
        # Helpers reachable from the filter, keyed by name.
        self.helpers: dict[str, HelperFunction] = {}
        # Per-helper, observed parameter ref/type info.
        self.helper_params: dict[str, list[HelperRefInfo]] = {}
        # Helper FunctionDef AST nodes, keyed by helper name.
        self.helper_asts: dict[str, ast.FunctionDef] = {}

        self._discover_helpers()
        self._parse_helpers()

    # ──────────────────────────────────────────────────────────────────
    # Helper discovery
    # ──────────────────────────────────────────────────────────────────

    def _discover_helpers(self) -> None:
        globs = self.filt.fn.__globals__
        # Walk filter AST + every helper AST repeatedly to find transitive helpers.
        seen: set[str] = set()
        queue: list[ast.AST] = [self._fn_def(self.filt.source)]
        while queue:
            node = queue.pop()
            for sub in ast.walk(node):
                if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Name):
                    nm = sub.func.id
                    if nm in seen:
                        continue
                    obj = globs.get(nm)
                    if isinstance(obj, HelperFunction):
                        seen.add(nm)
                        self.helpers[nm] = obj
                        queue.append(self._fn_def(obj.source))

    def _parse_helpers(self) -> None:
        for name, h in self.helpers.items():
            fd = self._fn_def(h.source)
            self.helper_asts[name] = fd
            self.helper_params[name] = [HelperRefInfo() for _ in fd.args.args]

    @staticmethod
    def _fn_def(source: str) -> ast.FunctionDef:
        tree = ast.parse(textwrap.dedent(source))
        for node in tree.body:
            if isinstance(node, ast.FunctionDef):
                return node
        raise RuntimeError(f"No function definition in source:\n{source}")

    # ──────────────────────────────────────────────────────────────────
    # Public entry point
    # ──────────────────────────────────────────────────────────────────

    def transpile(self) -> str:
        # First pass: transpile filter to learn helper call signatures.
        self._emit_function(self._fn_def(self.filt.source), is_filter=True, dry_run=True)

        # Second pass: actually emit. Helpers first (forward-declare-free order
        # achieved by emitting them in dependency order — but for simplicity
        # we emit each helper whose ref/type info is now known).
        out: list[str] = []
        out.append('#include "lib/immolate.cl"')
        out.append("")
        if self.filt.raw_helpers:
            out.append(self.filt.raw_helpers.strip())
            out.append("")
        for name in self._helper_emit_order():
            out.append(self._emit_helper(name))
            out.append("")
        out.append(self._emit_function(self._fn_def(self.filt.source), is_filter=True))
        return "\n".join(out) + "\n"

    def _helper_emit_order(self) -> list[str]:
        # Compute call-graph order: a helper that calls another must come
        # after it (so C sees declarations first).
        order: list[str] = []
        visited: set[str] = set()

        def visit(n: str) -> None:
            if n in visited:
                return
            visited.add(n)
            fd = self.helper_asts[n]
            for sub in ast.walk(fd):
                if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Name):
                    if sub.func.id in self.helpers:
                        visit(sub.func.id)
            order.append(n)

        for h in self.helpers:
            visit(h)
        return order

    # ──────────────────────────────────────────────────────────────────
    # Function emission
    # ──────────────────────────────────────────────────────────────────

    def _emit_helper(self, name: str) -> str:
        fd = self.helper_asts[name]
        ref_infos = self.helper_params[name]

        # Validate ref consistency: each param must be referenced consistently.
        for i, info in enumerate(ref_infos):
            if info.saw_ref and info.saw_value:
                pname = fd.args.args[i].arg
                raise SyntaxError(
                    f"Helper {name!r} parameter {pname!r} is passed both "
                    "by-ref (ref(...)) and by-value across call sites; pick one."
                )
            info.by_ref = info.saw_ref

        # Determine return type from the body.
        ret_type = self._infer_function_return_type(fd, name)

        # Build param list.
        params: list[str] = ["instance* inst"]
        scope = Scope()
        for i, arg in enumerate(fd.args.args):
            info = ref_infos[i]
            ty = info.inferred_type
            if info.by_ref:
                params.append(f"{ty}* {arg.arg}")
                scope.ref_params.add(arg.arg)
                scope.declared[arg.arg] = ty
            else:
                params.append(f"{ty} {arg.arg}")
                scope.declared[arg.arg] = ty

        body = self._emit_block(fd.body, scope, indent=1)
        sig = f"{ret_type} {name}({', '.join(params)}) {{\n{body}}}"
        return sig

    def _emit_function(
        self,
        fd: ast.FunctionDef,
        *,
        is_filter: bool,
        dry_run: bool = False,
    ) -> str:
        scope = Scope()
        if dry_run:
            self._emit_block(fd.body, scope, indent=1, dry_run=True)
            return ""
        body = self._emit_block(fd.body, scope, indent=1)
        if is_filter:
            return f"long filter(instance* inst) {{\n{body}}}"
        raise RuntimeError("non-filter, non-helper top-level not supported")

    def _infer_function_return_type(self, fd: ast.FunctionDef, name: str) -> str:
        # If no `return` statement found, void; otherwise infer from the first
        # return-value's expression type using a permissive empty scope.
        for sub in ast.walk(fd):
            if isinstance(sub, ast.Return):
                if sub.value is None:
                    return "void"
                inferred = self._infer_value_type(sub.value, Scope())
                # `long` is the safe widening choice; only narrow when we know
                # the value is bool.
                if inferred == "bool":
                    return "bool"
                return "long"
        return "void"

    # ──────────────────────────────────────────────────────────────────
    # Block & statement emission
    # ──────────────────────────────────────────────────────────────────

    def _emit_block(
        self,
        stmts: list[ast.stmt],
        scope: Scope,
        indent: int,
        *,
        dry_run: bool = False,
    ) -> str:
        ind = "    " * indent
        out: list[str] = []
        for stmt in stmts:
            out.append(self._emit_stmt(stmt, scope, indent, dry_run=dry_run))
        if dry_run:
            return ""
        return "".join(s for s in out if s) if False else "\n".join(s for s in out if s) + ("\n" if out else "")

    def _emit_stmt(
        self,
        stmt: ast.stmt,
        scope: Scope,
        indent: int,
        *,
        dry_run: bool,
    ) -> str:
        ind = "    " * indent

        if isinstance(stmt, ast.Assign):
            return self._emit_assign(stmt, scope, indent, dry_run=dry_run)
        if isinstance(stmt, ast.AugAssign):
            if dry_run:
                self._dry_visit_expr(stmt.value, scope)
                return ""
            target = self._emit_expr(stmt.target, scope)
            value = self._emit_expr(stmt.value, scope)
            op = _AUGOP[type(stmt.op)]
            return f"{ind}{target} {op} {value};"
        if isinstance(stmt, ast.If):
            return self._emit_if(stmt, scope, indent, dry_run=dry_run)
        if isinstance(stmt, ast.While):
            return self._emit_while(stmt, scope, indent, dry_run=dry_run)
        if isinstance(stmt, ast.For):
            return self._emit_for(stmt, scope, indent, dry_run=dry_run)
        if isinstance(stmt, ast.Return):
            if dry_run:
                if stmt.value is not None:
                    self._dry_visit_expr(stmt.value, scope)
                return ""
            if stmt.value is None:
                return f"{ind}return;"
            return f"{ind}return {self._emit_expr(stmt.value, scope)};"
        if isinstance(stmt, ast.Break):
            return "" if dry_run else f"{ind}break;"
        if isinstance(stmt, ast.Continue):
            return "" if dry_run else f"{ind}continue;"
        if isinstance(stmt, ast.Expr):
            if dry_run:
                self._dry_visit_expr(stmt.value, scope)
                return ""
            return f"{ind}{self._emit_expr(stmt.value, scope)};"
        if isinstance(stmt, ast.Pass):
            return ""
        raise SyntaxError(f"Unsupported statement: {ast.dump(stmt)}")

    # ──────────────────────────────────────────────────────────────────
    # Assignments — declarations vs reassignments
    # ──────────────────────────────────────────────────────────────────

    def _emit_assign(
        self,
        node: ast.Assign,
        scope: Scope,
        indent: int,
        *,
        dry_run: bool,
    ) -> str:
        ind = "    " * indent
        if len(node.targets) != 1:
            raise SyntaxError("Multiple assignment targets unsupported")
        target = node.targets[0]
        value = node.value

        # Tuple unpacking is no longer needed since we use ref() for mutation.
        if isinstance(target, ast.Tuple):
            raise SyntaxError(
                "Tuple unpacking unsupported. Use ref() at the call site for "
                "pass-by-reference helper outputs."
            )

        # Subscript / attribute assignment — never declares.
        if isinstance(target, (ast.Subscript, ast.Attribute)):
            if dry_run:
                self._dry_visit_expr(value, scope)
                return ""
            return f"{ind}{self._emit_expr(target, scope)} = {self._emit_expr(value, scope)};"

        if not isinstance(target, ast.Name):
            raise SyntaxError(f"Unsupported assignment target: {ast.dump(target)}")

        name = target.id

        # Detect array constructors at RHS.
        arr = self._match_array_constructor(value)
        if arr is not None:
            elem_ty, size_expr, init_list = arr
            if dry_run:
                return ""
            scope.declared[name] = f"{elem_ty}[]"
            if init_list is not None:
                init_str = ", ".join(self._emit_expr(e, scope) for e in init_list)
                return f"{ind}{elem_ty} {name}[{size_expr}] = {{{init_str}}};"
            return f"{ind}{elem_ty} {name}[{size_expr}];"

        if dry_run:
            self._dry_visit_expr(value, scope)
            # Track type so subsequent calls in the dry-run can resolve refs.
            scope.declared.setdefault(name, self._infer_value_type(value, scope))
            return ""

        rhs = self._emit_expr(value, scope)
        if name in scope.ref_params:
            return f"{ind}(*{name}) = {rhs};"
        if name in scope.declared:
            return f"{ind}{name} = {rhs};"
        ty = self._infer_value_type(value, scope)
        scope.declared[name] = ty
        return f"{ind}{ty} {name} = {rhs};"

    def _match_array_constructor(self, value: ast.expr) -> tuple[str, str, list[ast.expr] | None] | None:
        """Recognise `item_array(n)`, `int_array(n)`, `int_array([1,2,3])`."""
        if not isinstance(value, ast.Call):
            return None
        if not isinstance(value.func, ast.Name):
            return None
        fname = value.func.id
        if fname not in {"item_array", "int_array"}:
            return None
        elem_ty = "item" if fname == "item_array" else "int"
        if len(value.args) == 0:
            raise SyntaxError(f"{fname}() requires a size argument")
        first = value.args[0]
        # Form 1: int_array([a, b, c]) — size from list length, init from list.
        if isinstance(first, ast.List):
            return elem_ty, str(len(first.elts)), list(first.elts)
        # Form 2: <fn>(n) or <fn>(n, [a,b,c])
        size_expr = self._emit_expr_static(first)
        init_list: list[ast.expr] | None = None
        if len(value.args) >= 2:
            second = value.args[1]
            if isinstance(second, ast.List):
                init_list = list(second.elts)
            else:
                raise SyntaxError(f"{fname} second argument must be a list literal")
        return elem_ty, size_expr, init_list

    @staticmethod
    def _emit_expr_static(node: ast.expr) -> str:
        """Best-effort emit for a constant-like expression usable in an array size."""
        if isinstance(node, ast.Constant) and isinstance(node.value, int):
            return str(node.value)
        if isinstance(node, ast.Name):
            return node.id
        # For more complex sizes, fall through to ast.unparse.
        return ast.unparse(node)

    # ──────────────────────────────────────────────────────────────────
    # Type inference
    # ──────────────────────────────────────────────────────────────────

    def _infer_value_type(self, value: ast.expr, scope: Scope) -> str:
        if isinstance(value, ast.Constant):
            v = value.value
            if isinstance(v, bool):
                return "bool"
            if isinstance(v, int):
                return "long"
            if isinstance(v, float):
                return "double"
            raise SyntaxError(f"Unsupported literal type: {type(v).__name__}")
        if isinstance(value, ast.Name):
            return scope.declared.get(value.id, "long")
        if isinstance(value, ast.Call):
            if isinstance(value.func, ast.Name):
                fname = value.func.id
                sig = API_SIGNATURES.get(fname)
                if sig is not None:
                    return sig["returns"]
                if fname in self.helpers:
                    fd = self.helper_asts[fname]
                    return self._infer_function_return_type(fd, fname)
            return "long"
        if isinstance(value, ast.Attribute):
            return self._attribute_type(value, scope)
        if isinstance(value, ast.Subscript):
            base_ty = self._expr_type(value.value, scope)
            if base_ty.endswith("[]"):
                return base_ty[:-2]
            return "long"
        if isinstance(value, ast.BoolOp):
            return "bool"
        if isinstance(value, ast.Compare):
            return "bool"
        if isinstance(value, ast.UnaryOp):
            if isinstance(value.op, ast.Not):
                return "bool"
            return self._infer_value_type(value.operand, scope)
        if isinstance(value, ast.BinOp):
            return self._infer_value_type(value.left, scope)
        if isinstance(value, ast.IfExp):
            return self._infer_value_type(value.body, scope)
        return "long"

    def _expr_type(self, value: ast.expr, scope: Scope) -> str:
        return self._infer_value_type(value, scope)

    def _attribute_type(self, node: ast.Attribute, scope: Scope) -> str:
        # Walk the chain. inst.* and inst.params.* are special-cased.
        if isinstance(node.value, ast.Name) and node.value.id == "inst":
            field = node.attr
            if field in {"hashed_seed"}:
                return "double"
            return "long"  # locked / params returns are handled elsewhere
        # struct field
        base = self._expr_type(node.value, scope)
        fmap = _STRUCT_FIELDS.get(base)
        if fmap is not None and node.attr in fmap:
            return fmap[node.attr][1]
        return "long"

    # ──────────────────────────────────────────────────────────────────
    # Expression emission
    # ──────────────────────────────────────────────────────────────────

    def _emit_expr(self, node: ast.expr, scope: Scope) -> str:
        if isinstance(node, ast.Constant):
            v = node.value
            if isinstance(v, bool):
                return "true" if v else "false"
            if isinstance(v, (int, float)):
                return str(v)
            if isinstance(v, str):
                return f'"{v}"'
            raise SyntaxError(f"Unsupported literal: {v!r}")
        if isinstance(node, ast.Name):
            if node.id in scope.ref_params:
                return f"(*{node.id})"
            return node.id
        if isinstance(node, ast.Attribute):
            return self._emit_attribute(node, scope)
        if isinstance(node, ast.Subscript):
            base = self._emit_expr(node.value, scope)
            idx = self._emit_expr(self._slice_value(node.slice), scope)
            return f"{base}[{idx}]"
        if isinstance(node, ast.UnaryOp):
            op = _UNARYOP[type(node.op)]
            return f"{op}({self._emit_expr(node.operand, scope)})"
        if isinstance(node, ast.BinOp):
            l = self._emit_expr(node.left, scope)
            r = self._emit_expr(node.right, scope)
            op = _BINOP[type(node.op)]
            return f"({l} {op} {r})"
        if isinstance(node, ast.BoolOp):
            op = _BOOLOP[type(node.op)]
            parts = [self._emit_expr(v, scope) for v in node.values]
            return "(" + f" {op} ".join(parts) + ")"
        if isinstance(node, ast.Compare):
            parts: list[str] = []
            left = self._emit_expr(node.left, scope)
            cur_left = left
            for op_node, right in zip(node.ops, node.comparators):
                cur_right = self._emit_expr(right, scope)
                op = _CMPOP[type(op_node)]
                parts.append(f"({cur_left} {op} {cur_right})")
                cur_left = cur_right
            return " && ".join(parts) if len(parts) > 1 else parts[0]
        if isinstance(node, ast.Call):
            return self._emit_call(node, scope)
        if isinstance(node, ast.IfExp):
            cond = self._emit_expr(node.test, scope)
            t = self._emit_expr(node.body, scope)
            f = self._emit_expr(node.orelse, scope)
            return f"({cond} ? {t} : {f})"
        if isinstance(node, ast.NameConstant):  # py<3.8 compat (no-op for 3.10+)
            return "true" if node.value else "false"
        raise SyntaxError(f"Unsupported expression: {ast.dump(node)}")

    @staticmethod
    def _slice_value(s: ast.AST) -> ast.expr:
        if isinstance(s, ast.Index):  # python <3.9
            return s.value  # type: ignore[attr-defined]
        return s  # python >=3.9 already-an-expr

    def _emit_attribute(self, node: ast.Attribute, scope: Scope) -> str:
        # inst.X
        if isinstance(node.value, ast.Name) and node.value.id == "inst":
            mapped = INST_FIELD_MAP.get(node.attr, node.attr)
            return f"inst->{mapped}"
        # inst.params.X
        if (
            isinstance(node.value, ast.Attribute)
            and isinstance(node.value.value, ast.Name)
            and node.value.value.id == "inst"
            and node.value.attr == "params"
        ):
            mapped = PARAMS_FIELD_MAP.get(node.attr, node.attr)
            return f"inst->params.{mapped}"
        base = self._emit_expr(node.value, scope)
        # struct field: maybe rename via _STRUCT_FIELDS
        base_ty = self._expr_type(node.value, scope)
        fmap = _STRUCT_FIELDS.get(base_ty)
        attr = node.attr
        if fmap is not None and attr in fmap:
            attr = fmap[attr][0]
        return f"{base}.{attr}"

    # ──────────────────────────────────────────────────────────────────
    # Call emission
    # ──────────────────────────────────────────────────────────────────

    def _emit_call(self, node: ast.Call, scope: Scope) -> str:
        if not isinstance(node.func, ast.Name):
            raise SyntaxError(
                "Only direct function calls supported (no method/attribute calls)"
            )
        fname = node.func.id

        if fname == "ref":
            raise SyntaxError(
                "ref() is only allowed as a direct argument to a helper call"
            )
        if fname in {"item_array", "int_array"}:
            raise SyntaxError(
                f"{fname}() may only appear on the right-hand side of an assignment"
            )

        # API call — inject inst at the right position.
        sig = API_SIGNATURES.get(fname)
        if sig is not None:
            return self._emit_api_call(fname, sig, node.args, scope)

        # Helper call — first arg is inst; ref() args become &x.
        if fname in self.helpers:
            return self._emit_helper_call(fname, node.args, scope)

        # Unknown — assume it's a raw_helpers function that takes
        # `instance* inst` as its first parameter (matching Immolate convention).
        # Users whose raw helpers don't need inst can pass it through unused.
        args = ["inst"] + [self._emit_call_arg(a, scope) for a in node.args]
        return f"{fname}({', '.join(args)})"

    def _emit_api_call(
        self,
        fname: str,
        sig: dict,
        user_args: list[ast.expr],
        scope: Scope,
    ) -> str:
        params = sig["params"]
        # Build the C arg list in C parameter order. For each param: if it's the
        # `instance*` slot, emit `inst`; otherwise consume next user arg.
        out_args: list[str] = []
        u = 0
        for ty, _pname in params:
            if ty == "instance*":
                out_args.append("inst")
                continue
            if u >= len(user_args):
                raise SyntaxError(
                    f"{fname}() expected {len(params) - 1} args (excluding inst); "
                    f"got {len(user_args)}"
                )
            out_args.append(self._emit_call_arg(user_args[u], scope))
            u += 1
        if u != len(user_args):
            raise SyntaxError(
                f"{fname}() got {len(user_args)} args but expected "
                f"{len(params) - sum(1 for t, _ in params if t == 'instance*')}"
            )
        return f"{fname}({', '.join(out_args)})"

    def _emit_helper_call(
        self,
        fname: str,
        user_args: list[ast.expr],
        scope: Scope,
    ) -> str:
        info_list = self.helper_params[fname]
        if len(user_args) != len(info_list):
            raise SyntaxError(
                f"helper {fname}() expected {len(info_list)} args, got {len(user_args)}"
            )
        out_args: list[str] = ["inst"]
        for i, arg in enumerate(user_args):
            info = info_list[i]
            ref_target = self._unwrap_ref(arg)
            if ref_target is not None:
                if not isinstance(ref_target, ast.Name):
                    raise SyntaxError(
                        f"ref() argument must be a variable name, got "
                        f"{ast.dump(ref_target)}"
                    )
                out_args.append(f"&{ref_target.id}")
            else:
                out_args.append(self._emit_expr(arg, scope))
        return f"{fname}({', '.join(out_args)})"

    @staticmethod
    def _unwrap_ref(node: ast.expr) -> ast.expr | None:
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "ref"
        ):
            if len(node.args) != 1:
                raise SyntaxError("ref() takes exactly one argument")
            return node.args[0]
        return None

    def _emit_call_arg(self, arg: ast.expr, scope: Scope) -> str:
        # ref() at non-helper-call sites is an error, caught above; for helpers
        # we use _emit_helper_call which special-cases ref().
        if (
            isinstance(arg, ast.Call)
            and isinstance(arg.func, ast.Name)
            and arg.func.id == "ref"
        ):
            raise SyntaxError("ref() not allowed here")
        return self._emit_expr(arg, scope)

    # ──────────────────────────────────────────────────────────────────
    # If / While / For
    # ──────────────────────────────────────────────────────────────────

    def _emit_if(
        self, stmt: ast.If, scope: Scope, indent: int, *, dry_run: bool
    ) -> str:
        ind = "    " * indent
        if dry_run:
            self._dry_visit_expr(stmt.test, scope)
            self._emit_block(stmt.body, scope, indent + 1, dry_run=True)
            self._emit_block(stmt.orelse, scope, indent + 1, dry_run=True)
            return ""
        cond = self._emit_expr(stmt.test, scope)
        body = self._emit_block(stmt.body, scope, indent + 1)
        out = [f"{ind}if ({cond}) {{", body.rstrip("\n"), f"{ind}}}"]
        if stmt.orelse:
            # elif (single If in orelse) flattens cleanly
            if len(stmt.orelse) == 1 and isinstance(stmt.orelse[0], ast.If):
                else_str = self._emit_if(stmt.orelse[0], scope, indent, dry_run=False)
                else_str_lines = else_str.splitlines()
                # Merge "} if (...)" → "} else if (...)"
                if else_str_lines:
                    first = else_str_lines[0].lstrip()
                    out[-1] = f"{ind}}} else " + first
                    out.extend(else_str_lines[1:])
            else:
                else_body = self._emit_block(stmt.orelse, scope, indent + 1)
                out[-1] = f"{ind}}} else {{"
                out.append(else_body.rstrip("\n"))
                out.append(f"{ind}}}")
        return "\n".join(out)

    def _emit_while(
        self, stmt: ast.While, scope: Scope, indent: int, *, dry_run: bool
    ) -> str:
        ind = "    " * indent
        if dry_run:
            self._dry_visit_expr(stmt.test, scope)
            self._emit_block(stmt.body, scope, indent + 1, dry_run=True)
            return ""
        cond = self._emit_expr(stmt.test, scope)
        body = self._emit_block(stmt.body, scope, indent + 1)
        return f"{ind}while ({cond}) {{\n{body.rstrip(chr(10))}\n{ind}}}"

    def _emit_for(
        self, stmt: ast.For, scope: Scope, indent: int, *, dry_run: bool
    ) -> str:
        ind = "    " * indent
        # Only `for x in range(...)` supported.
        if not (
            isinstance(stmt.iter, ast.Call)
            and isinstance(stmt.iter.func, ast.Name)
            and stmt.iter.func.id == "range"
        ):
            raise SyntaxError("Only `for x in range(...)` is supported")
        if not isinstance(stmt.target, ast.Name):
            raise SyntaxError("for-loop target must be a simple name")

        var = stmt.target.id
        args = stmt.iter.args
        if len(args) == 1:
            start, stop, step = "0", self._emit_expr(args[0], scope), "1"
        elif len(args) == 2:
            start = self._emit_expr(args[0], scope)
            stop = self._emit_expr(args[1], scope)
            step = "1"
        elif len(args) == 3:
            start = self._emit_expr(args[0], scope)
            stop = self._emit_expr(args[1], scope)
            step = self._emit_expr(args[2], scope)
        else:
            raise SyntaxError("range() takes 1-3 arguments")

        loop_scope = Scope(declared={**scope.declared, var: "long"}, ref_params=set(scope.ref_params))
        if dry_run:
            self._emit_block(stmt.body, loop_scope, indent + 1, dry_run=True)
            return ""
        body = self._emit_block(stmt.body, loop_scope, indent + 1)
        step_clause = (
            f"{var}++" if step == "1"
            else f"{var}--" if step == "-1"
            else f"{var} += {step}"
        )
        return (
            f"{ind}for (long {var} = {start}; {var} < {stop}; {step_clause}) {{\n"
            f"{body.rstrip(chr(10))}\n{ind}}}"
        )

    # ──────────────────────────────────────────────────────────────────
    # Dry-run (first pass): record helper call signatures
    # ──────────────────────────────────────────────────────────────────

    def _dry_visit_expr(self, node: ast.expr, scope: Scope) -> None:
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            fname = node.func.id
            if fname in self.helpers:
                self._dry_record_helper_call(fname, node.args, scope)
            for a in node.args:
                self._dry_visit_expr(a, scope)
            return
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.expr):
                self._dry_visit_expr(child, scope)

    def _dry_record_helper_call(
        self, fname: str, user_args: list[ast.expr], scope: Scope
    ) -> None:
        infos = self.helper_params[fname]
        if len(user_args) != len(infos):
            return
        for i, arg in enumerate(user_args):
            ref_target = self._unwrap_ref(arg)
            info = infos[i]
            if ref_target is not None:
                info.saw_ref = True
                if isinstance(ref_target, ast.Name):
                    info.inferred_type = scope.declared.get(
                        ref_target.id, info.inferred_type
                    )
            else:
                info.saw_value = True
                # Try to infer from constant or a known name's type.
                if isinstance(arg, ast.Constant) and isinstance(arg.value, bool):
                    info.inferred_type = "bool"
                elif isinstance(arg, ast.Constant) and isinstance(arg.value, int):
                    info.inferred_type = "int"
                elif isinstance(arg, ast.Name) and arg.id in scope.declared:
                    info.inferred_type = scope.declared[arg.id]


def generate_cl(filt: FilterFunction) -> tuple[str, str]:
    """Transpile a `@filter` to a `.cl` source. Returns (filter_name, cl_source)."""
    if not isinstance(filt, FilterFunction):
        raise TypeError(
            f"generate_cl expects a @filter-decorated function, got {type(filt).__name__}"
        )
    return filt.name, Transpiler(filt).transpile()
