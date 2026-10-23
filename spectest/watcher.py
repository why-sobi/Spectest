"""`spectest watch`: re-runs the agent whenever the spec or source files change."""
import time
from pathlib import Path

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from spectest.config import load_config
from spectest.tools.spec_reader import is_skipped

DEBOUNCE_SECONDS = 2.0


class ChangeHandler(FileSystemEventHandler):
    def __init__(self, root: Path, watched_files: set[Path], exclude: frozenset[str]):
        self.root = root
        self.watched_files = {f.resolve() for f in watched_files}
        self.exclude = exclude
        self.last_change = 0.0

    def on_any_event(self, event):
        if event.is_directory or event.event_type not in ("created", "modified", "moved", "deleted"):
            return
        for raw in (event.src_path, getattr(event, "dest_path", "")):
            if not raw:
                continue
            path = Path(raw).resolve()
            if path in self.watched_files or (
                path.suffix == ".py" and path.is_relative_to(self.root)
                and not is_skipped(path.relative_to(self.root).parts[:-1], self.exclude)
            ):
                self.last_change = time.monotonic()


def watch(root: Path | str, run_agent):
    cfg = load_config(root)
    handler = ChangeHandler(cfg.root, {cfg.spec_path, cfg.config_file}, cfg.exclude)
    observer = Observer()
    # watch each source folder once (skip folders nested inside another source folder)
    tops = {d for d in cfg.source_dirs if not any(d != o and d.is_relative_to(o) for o in cfg.source_dirs)}
    for folder in {cfg.spec_path.parent.resolve(), cfg.config_file.parent.resolve()} - tops:
        observer.schedule(handler, str(folder), recursive=False)
    for folder in tops:
        observer.schedule(handler, str(folder), recursive=True)
    observer.start()
    names = ", ".join(sorted(d.relative_to(cfg.root).as_posix() or "." for d in tops))
    print(f"[spectest] watching {cfg.spec_path.name}, {cfg.config_file.name} and {names} (Ctrl+C to stop)")

    run_agent(cfg.root)  # initial check
    try:
        while True:
            time.sleep(0.5)
            # Wait until edits settle so one save (or a burst of saves) triggers a single run.
            if handler.last_change and time.monotonic() - handler.last_change >= DEBOUNCE_SECONDS:
                handler.last_change = 0.0
                if not cfg.config_file.exists():  # `spectest remove` (or a manual delete) ended this project
                    print(f"[spectest] {cfg.config_file.name} is gone; stopping watch")
                    break
                print("[spectest] change detected")
                run_agent(cfg.root)
    except KeyboardInterrupt:
        pass
    finally:
        observer.stop()
        observer.join()
