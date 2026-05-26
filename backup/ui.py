"""
Console UI helpers — uses `rich` when available, degrades to plain text when not.

`rich` is an OPTIONAL dependency (pip install rich, or -r requirements-ui.txt).
Everything works without it. Output is ASCII-only by design ([LEVEL] tags, not
emoji) so it never crashes on a legacy Windows console (cp1252); rich is used
purely for color, and unicode-heavy widgets (rule lines, progress bars) are
gated to terminals that can render them.

stdout = progress/info, stderr = warnings/errors (Jenkins log readability).
"""
import getpass
import sys
from contextlib import contextmanager

# Best-effort: never crash on a stray non-ASCII byte in the plain path.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

try:
    from rich.console import Console
    from rich.progress import (Progress, BarColumn, DownloadColumn,
                               TextColumn, TimeElapsedColumn, TransferSpeedColumn)
    from rich.prompt import Prompt, Confirm
    from rich.table import Table
    _con = Console()
    _err = Console(stderr=True)
    HAVE_RICH = True
    # Box-drawing / progress glyphs are unsafe on the legacy Windows console.
    RICH_UNICODE = not _con.legacy_windows
except ImportError:                                # pragma: no cover - env dependent
    _con = _err = None
    HAVE_RICH = RICH_UNICODE = False


def section(title: str) -> None:
    if RICH_UNICODE:
        _con.rule(f"[bold cyan]{title}")
    elif HAVE_RICH:
        _con.print(f"[bold cyan]== {title} ==[/]")
    else:
        print(f"\n=== {title} ===")


def info(msg: str) -> None:
    _con.print(f"[cyan][INFO][/] {msg}") if HAVE_RICH else print(f"[INFO] {msg}")


def ok(msg: str) -> None:
    _con.print(f"[green][OK][/] {msg}") if HAVE_RICH else print(f"[OK] {msg}")


def warn(msg: str) -> None:
    _err.print(f"[yellow][WARN][/] {msg}") if HAVE_RICH \
        else print(f"[WARN] {msg}", file=sys.stderr)


def error(msg: str) -> None:
    _err.print(f"[red][ERROR][/] {msg}") if HAVE_RICH \
        else print(f"[ERROR] {msg}", file=sys.stderr)


def prompt(label: str, default: str | None = None, secret: bool = False) -> str:
    if secret:
        val = getpass.getpass(f"{label}: ")
        return val or (default or "")
    if HAVE_RICH:
        return Prompt.ask(label, default=default or None) or ""
    suffix = f" [{default}]" if default else ""
    val = input(f"{label}{suffix}: ").strip()
    return val or (default or "")


def confirm(label: str, default: bool = False) -> bool:
    if HAVE_RICH:
        return Confirm.ask(label, default=default)
    d = "Y/n" if default else "y/N"
    val = input(f"{label} [{d}]: ").strip().lower()
    return default if not val else val in ("y", "yes")


def table(title: str, rows: list[tuple[str, str]]) -> None:
    """Two-column key/value table (ASCII-safe: no box borders)."""
    if HAVE_RICH:
        t = Table(title=title or None, show_header=False, box=None)
        t.add_column(style="bold")
        t.add_column()
        for k, v in rows:
            t.add_row(k, v)
        _con.print(t)
    else:
        if title:
            print(title)
        width = max((len(k) for k, _ in rows), default=0)
        for k, v in rows:
            print(f"  {k.ljust(width)} : {v}")


@contextmanager
def progress_bar(total: int | None, description: str):
    """
    Context manager yielding an `update(n_bytes)` callable for streaming
    transfers. `total` may be None when the size is unknown. Falls back to
    periodic percentage prints when a rich progress bar isn't safe to render.
    """
    if RICH_UNICODE:
        cols = [TextColumn("[progress.description]{task.description}"), BarColumn(),
                DownloadColumn(), TransferSpeedColumn(), TimeElapsedColumn()]
        with Progress(*cols, console=_con, transient=True) as prog:
            task = prog.add_task(description, total=total)
            yield lambda n: prog.update(task, advance=n)
    else:
        state = {"done": 0, "last": -1}

        def update(n: int) -> None:
            state["done"] += n
            if total:
                pct = int(state["done"] * 100 / total)
                if pct != state["last"] and pct % 10 == 0:
                    print(f"  {description}: {pct}%")
                    state["last"] = pct

        print(f"  {description}: starting"
              + (f" ({total / 1048576:.1f} MB)" if total else ""))
        yield update
        print(f"  {description}: done ({state['done'] / 1048576:.1f} MB)")


@contextmanager
def status(description: str):
    """Spinner/status for indefinite waits (e.g. polling)."""
    if RICH_UNICODE:
        with _con.status(description):
            yield
    else:
        print(f"  {description}")
        yield
