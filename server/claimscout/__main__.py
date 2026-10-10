"""claimscout serve | refresh | pair | open | status"""
import argparse
import asyncio
import json
import webbrowser

from . import pairing
from .db import DB, HOME

API_PORT, WEB_PORT = 8787, 8788


async def serve(db, api_port, web_port):
    import uvicorn
    from .app import Hub, create_app
    hub = Hub(db, api_port)
    cert, key = pairing.ensure_cert()
    api = uvicorn.Server(uvicorn.Config(create_app(db, api_port, hub=hub), host="0.0.0.0", port=api_port,
                                        ssl_certfile=str(cert), ssl_keyfile=str(key), log_level="warning"))
    web = uvicorn.Server(uvicorn.Config(create_app(db, api_port, dashboard=True, hub=hub), host="127.0.0.1",
                                        port=web_port, log_level="warning"))
    print(f"ClaimScout {HOME}\n  phone API  https://0.0.0.0:{api_port}  (cert {pairing.fingerprint()[:16]}…)\n"
          f"  dashboard  http://127.0.0.1:{web_port}/#t={pairing.token(db)}", flush=True)
    loop = asyncio.create_task(hub.loop())
    try:
        await asyncio.gather(api.serve(), web.serve())
    finally:
        loop.cancel()


def main():
    ap = argparse.ArgumentParser(prog="claimscout")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("serve", help="run the phone API and the dashboard")
    s.add_argument("--port", type=int, default=API_PORT)
    s.add_argument("--web-port", type=int, default=WEB_PORT)
    sub.add_parser("refresh", help="pull settlements and score them now")
    sub.add_parser("pair", help="print the pairing link and QR code for the phone")
    sub.add_parser("reset-token", help="unpair every phone")
    sub.add_parser("open", help="open the dashboard in a browser")
    a = ap.parse_args()
    db = DB()
    if a.cmd == "serve":
        asyncio.run(serve(db, a.port, a.web_port))
    elif a.cmd == "refresh":
        from .app import Hub
        print(json.dumps(asyncio.run(Hub(db).refresh()), indent=2))
    elif a.cmd == "pair":
        import qrcode
        link = pairing.link(db, API_PORT)
        q = qrcode.QRCode(border=1)
        q.add_data(link)
        q.print_ascii(invert=True)
        print(link)
    elif a.cmd == "reset-token":
        pairing.reset_token(db)
        print("Every phone is unpaired. Run `claimscout pair` to pair again.")
    elif a.cmd == "open":
        webbrowser.open(f"http://127.0.0.1:{WEB_PORT}/#t={pairing.token(db)}")


if __name__ == "__main__":
    main()
