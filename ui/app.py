"""
Rafiq Voice AI - Python Desktop & Web Application
Runs the modern minimal UI in a native desktop window (via pywebview)
or serves it to the browser.
"""
import argparse
import http.server
import os
import socket
import socketserver
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

# Paths
BASE_DIR = Path(__file__).resolve().parent.parent
UI_DIR = Path(__file__).resolve().parent
INDEX_HTML = UI_DIR / "index.html"


def is_port_in_use(port: int, host: str = "127.0.0.1") -> bool:
    """Check if a network port is already bound."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex((host, port)) == 0


def ensure_server_running(host: str = "127.0.0.1", port: int = 8765):
    """If the Rafiq WebSocket server is not running, launch it in the background."""
    if is_port_in_use(port, host):
        print(f"[+] Rafiq WebSocket server is already active on ws://{host}:{port}")
        return None

    print(f"[*] Starting Rafiq WebSocket server on ws://{host}:{port} ...")
    python_exe = sys.executable
    proc = subprocess.Popen(
        [python_exe, "-m", "server.server"],
        cwd=str(BASE_DIR),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    # Wait briefly for startup
    for _ in range(15):
        time.sleep(0.3)
        if is_port_in_use(port, host):
            print(f"[+] Rafiq server started successfully (PID: {proc.pid})")
            return proc
    print("[!] Warning: Server did not respond immediately, continuing...")
    return proc


class UIRequestHandler(http.server.SimpleHTTPRequestHandler):
    """Serves the UI directory with proper mime types and headers."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(UI_DIR), **kwargs)

    def log_message(self, format, *args):
        # Silence routine static asset HTTP logs
        pass


def run_http_server(port: int = 8766):
    """Start local HTTP server to host the UI assets."""
    handler = UIRequestHandler
    # Allow port reuse
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("127.0.0.1", port), handler) as httpd:
        httpd.serve_forever()


def main():
    parser = argparse.ArgumentParser(description="Rafiq Voice AI Modern UI")
    parser.add_argument("--browser", action="store_true", help="Launch in default web browser instead of native desktop window")
    parser.add_argument("--ui-port", type=int, default=8766, help="Port for the local UI web server (default: 8766)")
    parser.add_argument("--server-port", type=int, default=8765, help="Port for the WebSocket backend (default: 8765)")
    parser.add_argument("--no-server", action="store_true", help="Do not auto-start the Rafiq backend server")
    args = parser.parse_args()

    server_proc = None
    if not args.no_server:
        server_proc = ensure_server_running(port=args.server_port)

    # Start HTTP static server in daemon thread
    ui_port = args.ui_port
    while is_port_in_use(ui_port):
        ui_port += 1

    http_thread = threading.Thread(target=run_http_server, args=(ui_port,), daemon=True)
    http_thread.start()

    ui_url = f"http://127.0.0.1:{ui_port}/index.html"
    print(f"\n==========================================")
    print(f"  رفيق | Rafiq Voice Assistant")
    print(f"  UI URL: {ui_url}")
    print(f"  WebSocket: ws://127.0.0.1:{args.server_port}")
    print(f"==========================================\n")

    use_browser = args.browser

    if not use_browser:
        try:
            import webview

            print("[+] Launching native desktop window...")
            window = webview.create_window(
                title="رفيق | Rafiq Voice AI",
                url=ui_url,
                width=1060,
                height=790,
                min_size=(800, 600),
                background_color="#09090b",
                text_select=False,
            )
            webview.start(debug=False)
        except Exception as e:
            print(f"[!] pywebview desktop error ({e}). Falling back to browser...")
            use_browser = True

    if use_browser:
        print("[+] Opening UI in default web browser...")
        webbrowser.open(ui_url)
        print("Press Ctrl+C to stop the UI server.")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nShutting down...")

    if server_proc:
        try:
            server_proc.terminate()
        except Exception:
            pass


if __name__ == "__main__":
    main()
