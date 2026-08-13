import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ADMIN_HANDLER = ROOT / "app" / "bot" / "handlers" / "admin.py"
ADMIN_EXTENSIONS = ROOT / "app" / "bot" / "handlers" / "admin_extensions.py"


def _decorator_name(decorator: ast.expr) -> str:
    if not isinstance(decorator, ast.Call):
        return ""
    func = decorator.func
    if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
        return f"{func.value.id}.{func.attr}"
    return ""


def _calls(function: ast.AsyncFunctionDef, name: str) -> bool:
    for node in ast.walk(function):
        if not isinstance(node, ast.Call):
            continue
        target = node.func
        if isinstance(target, ast.Name) and target.id == name:
            return True
    return False


def _admin_functions(path: Path) -> list[ast.AsyncFunctionDef]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return [node for node in tree.body if isinstance(node, ast.AsyncFunctionDef)]


def test_every_main_admin_callback_revalidates_admin_account() -> None:
    functions = _admin_functions(ADMIN_HANDLER)
    callbacks = [
        fn
        for fn in functions
        if any(_decorator_name(item) == "router.callback_query" for item in fn.decorator_list)
    ]
    assert callbacks
    missing = [fn.name for fn in callbacks if not _calls(fn, "_require_callback_admin")]
    assert not missing, f"Admin callbacks without server-side admin revalidation: {missing}"


def test_every_main_admin_fsm_message_revalidates_admin_account() -> None:
    functions = _admin_functions(ADMIN_HANDLER)
    state_messages: list[ast.AsyncFunctionDef] = []
    for fn in functions:
        for decorator in fn.decorator_list:
            if _decorator_name(decorator) != "router.message" or not isinstance(decorator, ast.Call):
                continue
            if any(
                isinstance(arg, ast.Attribute)
                and isinstance(arg.value, ast.Name)
                and arg.value.id == "AdminStates"
                for arg in decorator.args
            ):
                state_messages.append(fn)
    assert state_messages
    missing = [fn.name for fn in state_messages if not _calls(fn, "_require_message_admin")]
    assert not missing, f"Admin FSM handlers without server-side admin revalidation: {missing}"


def test_admin_extensions_commands_and_callbacks_revalidate_admin_account() -> None:
    functions = _admin_functions(ADMIN_EXTENSIONS)
    guarded = []
    missing = []
    for fn in functions:
        decorators = {_decorator_name(item) for item in fn.decorator_list}
        if "router.message" in decorators:
            guarded.append(fn.name)
            if not _calls(fn, "_message_admin"):
                missing.append(fn.name)
        if "router.callback_query" in decorators:
            guarded.append(fn.name)
            if not _calls(fn, "_callback_admin"):
                missing.append(fn.name)
    assert guarded
    assert not missing, f"Admin extension handlers without server-side admin revalidation: {missing}"


def test_admin_guards_clear_fsm_when_privilege_is_lost() -> None:
    source = ADMIN_HANDLER.read_text(encoding="utf-8")
    extensions = ADMIN_EXTENSIONS.read_text(encoding="utf-8")
    assert source.count("await state.clear()") >= 5
    assert "if admin is None:" in source
    assert "await state.clear()" in extensions
    assert "if admin is None:" in extensions
