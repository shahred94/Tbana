"""Windows launcher for the packaged TBana Stream desktop application."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import socket
import sys
import threading
import time
import traceback
import urllib.request
import webbrowser


HOST = "127.0.0.1"
PORT = 8000
DASHBOARD_URL = f"http://{HOST}:{PORT}"


def _resource_root() -> Path:
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))


def _data_root() -> Path:
    local_app_data = os.getenv("LOCALAPPDATA")
    base = (
        Path(local_app_data)
        if local_app_data
        else Path.home() / "AppData" / "Local"
    )
    data_root = base / "TBana Stream"
    legacy_root = base / "LiveTrigger"
    if not data_root.exists() and legacy_root.exists():
        shutil.copytree(legacy_root, data_root, dirs_exist_ok=True)
    return data_root


def _load_environment(path: Path, *, override: bool = False) -> None:
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        name = name.strip()
        value = value.strip().strip("\"'")
        if name and (override or name not in os.environ):
            os.environ[name] = value


def prepare_runtime() -> tuple[Path, Path]:
    resource_root = _resource_root()
    data_root = _data_root()
    data_root.mkdir(parents=True, exist_ok=True)

    os.environ["TBANA_STREAM_RESOURCE_DIR"] = str(resource_root)
    os.environ["TBANA_STREAM_DATA_DIR"] = str(data_root)
    # Legacy aliases keep older integrations and extensions working.
    os.environ["LIVETRIGGER_RESOURCE_DIR"] = str(resource_root)
    os.environ["LIVETRIGGER_DATA_DIR"] = str(data_root)

    _load_environment(resource_root / "desktop.env")
    _load_environment(data_root / "config.env", override=True)

    user_sounds = data_root / "sounds"
    user_sounds.mkdir(parents=True, exist_ok=True)
    bundled_sounds = resource_root / "sounds"
    if bundled_sounds.exists():
        for source in bundled_sounds.iterdir():
            target = user_sounds / source.name
            if source.is_file() and not target.exists():
                shutil.copy2(source, target)

    os.chdir(data_root)
    return resource_root, data_root


def port_is_open() -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as connection:
        connection.settimeout(0.4)
        return connection.connect_ex((HOST, PORT)) == 0


def live_trigger_is_ready() -> bool:
    try:
        with urllib.request.urlopen(DASHBOARD_URL, timeout=1) as response:
            return response.status < 500
    except Exception:
        return False


def main() -> None:
    resource_root, data_root = prepare_runtime()

    import tkinter as tk
    from tkinter import messagebox

    if port_is_open():
        if live_trigger_is_ready():
            webbrowser.open(DASHBOARD_URL)
            messagebox.showinfo(
                "TBana Stream",
                "TBana Stream is already running. The dashboard has been opened.",
            )
        else:
            messagebox.showerror(
                "TBana Stream",
                "Port 8000 is being used by another application.\n\n"
                "Close that application and start TBana Stream again.",
            )
        return

    root = tk.Tk()
    root.title("TBana Stream")
    root.geometry("430x290")
    root.resizable(False, False)

    icon_path = resource_root / "assets" / "tibanakstream.ico"
    if icon_path.exists():
        try:
            root.iconbitmap(default=str(icon_path))
        except tk.TclError:
            pass

    background = "#111827"
    panel = "#1f2937"
    foreground = "#f9fafb"
    muted = "#9ca3af"
    accent = "#7c3aed"

    root.configure(bg=background)
    container = tk.Frame(root, bg=panel, padx=24, pady=22)
    container.pack(fill="both", expand=True, padx=14, pady=14)

    logo_path = (
        resource_root
        / "assets"
        / "tibanakstream-logo-cropped.png"
    )
    if logo_path.exists():
        logo_image = tk.PhotoImage(
            file=str(logo_path)
        ).subsample(7, 7)
        logo_label = tk.Label(
            container,
            image=logo_image,
            bg=panel,
            borderwidth=0,
        )
        logo_label.image = logo_image
        logo_label.pack(anchor="w")
    else:
        tk.Label(
            container,
            text="TBana Stream",
            bg=panel,
            fg=foreground,
            font=("Segoe UI", 18, "bold"),
        ).pack(anchor="w")

    status_text = tk.StringVar(value="Starting local dashboard…")
    tk.Label(
        container,
        textvariable=status_text,
        bg=panel,
        fg=muted,
        font=("Segoe UI", 10),
    ).pack(anchor="w", pady=(8, 18))

    button_row = tk.Frame(container, bg=panel)
    button_row.pack(fill="x")

    def open_dashboard() -> None:
        webbrowser.open(DASHBOARD_URL)

    open_button = tk.Button(
        button_row,
        text="Open Dashboard",
        command=open_dashboard,
        state="disabled",
        bg=accent,
        fg="#ffffff",
        activebackground="#6d28d9",
        activeforeground="#ffffff",
        relief="flat",
        padx=16,
        pady=8,
        font=("Segoe UI", 10, "bold"),
    )
    open_button.pack(side="left")

    server_holder: dict[str, object] = {}

    def stop_application() -> None:
        server = server_holder.get("server")
        if server is not None:
            server.should_exit = True
        root.after(150, root.destroy)

    tk.Button(
        button_row,
        text="Exit",
        command=stop_application,
        bg="#374151",
        fg=foreground,
        activebackground="#4b5563",
        activeforeground=foreground,
        relief="flat",
        padx=16,
        pady=8,
        font=("Segoe UI", 10),
    ).pack(side="left", padx=(10, 0))

    tk.Label(
        container,
        text="Keep this window open while using TBana Stream.",
        bg=panel,
        fg=muted,
        font=("Segoe UI", 9),
    ).pack(anchor="w", pady=(20, 0))

    def run_server() -> None:
        try:
            import uvicorn
            from app.main import app

            config = uvicorn.Config(
                app,
                host=HOST,
                port=PORT,
                log_level="warning",
                access_log=False,
                log_config=None,
            )
            server = uvicorn.Server(config)
            server_holder["server"] = server
            server.run()
        except Exception as error:
            (data_root / "launcher-error.log").write_text(
                traceback.format_exc(),
                encoding="utf-8",
            )
            error_message = f"{type(error).__name__}: {error}"
            root.after(
                0,
                lambda: status_text.set(
                    f"Unable to start TBana Stream: {error_message}"
                ),
            )

    threading.Thread(target=run_server, daemon=True).start()

    def wait_for_server() -> None:
        for _ in range(80):
            if live_trigger_is_ready():
                root.after(0, lambda: status_text.set("● Connected — Ready"))
                root.after(0, lambda: open_button.config(state="normal"))
                root.after(0, open_dashboard)
                return
            time.sleep(0.25)
        root.after(
            0,
            lambda: status_text.set(
                "Unable to start the dashboard. Close and try again."
            ),
        )

    threading.Thread(target=wait_for_server, daemon=True).start()
    root.protocol("WM_DELETE_WINDOW", stop_application)
    root.mainloop()


if __name__ == "__main__":
    main()
