"""Start the interactive demo app.   python scripts/run_app.py   (from the thermal/ folder)

Opens http://127.0.0.1:8765 in your browser. The server only listens on this machine.
No camera is opened unless you click Connect on the Device screen.
"""

import argparse
import threading
import webbrowser

import uvicorn

from thermal.app.server import create_app

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-browser", action="store_true", help="do not open a browser tab")
    args = ap.parse_args()
    url = f"http://127.0.0.1:{args.port}"
    if not args.no_browser:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    print(f"Thermal Respiratory Sensing demo: {url}  (Ctrl+C to stop)")
    uvicorn.run(create_app(), host="127.0.0.1", port=args.port, log_level="warning")
