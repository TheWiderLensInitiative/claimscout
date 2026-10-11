"""claimscout serve | refresh | pair | open | doctor | reset-token"""
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


def doctor(db):
    """Plain-language checks for the usual problems: server down, port blocked, wrong address, sources failing."""
    import shutil
    import socket
    import ssl
    import subprocess
    import time
    good = lambda m: print(f"  \033[32m✓\033[0m {m}")
    bad = lambda m, fix: print(f"  \033[31m✗\033[0m {m}\n      → {fix}")
    note = lambda m: print(f"  \033[33m!\033[0m {m}")

    def reach(host, port, tls=False):
        try:
            with socket.create_connection((host, port), timeout=3) as s:
                if tls:
                    ctx = ssl.create_default_context()
                    ctx.check_hostname, ctx.verify_mode = False, ssl.CERT_NONE
                    ctx.wrap_socket(s).close()
            return True
        except OSError:
            return False

    print("ClaimScout doctor\n")
    up = reach("127.0.0.1", WEB_PORT) and reach("127.0.0.1", API_PORT, tls=True)
    if up:
        good(f"the server is running (phone port {API_PORT}, dashboard port {WEB_PORT})")
    else:
        bad("the server isn't running", "start it: systemctl --user restart claimscout   (or: claimscout serve)\n"
            "        see why it stopped: journalctl --user -u claimscout -n 50")
    addrs = pairing.addresses()
    lan = [a for a in addrs if not a.startswith("100.") and a != "127.0.0.1"]
    if lan:
        good(f"home network address: {', '.join(lan)}")
        for a in lan:
            if up and not reach(a, API_PORT, tls=True):
                bad(f"port {API_PORT} doesn't answer on {a}", "something on this PC blocks it; re-run ./install.sh")
    else:
        bad("this PC has no home network address", "connect it to Wi-Fi or Ethernet")
    if shutil.which("tailscale"):
        ts = [a for a in addrs if a.startswith("100.")]
        good(f"Tailscale address: {ts[0]} (works away from home)") if ts else \
            note("Tailscale is installed but not connected: run `tailscale up`")
    else:
        note("no Tailscale: the phone can only reach this PC on the same Wi-Fi (free: https://tailscale.com/download)")
    fw = None
    try:
        if shutil.which("ufw") and "ENABLED=yes" in open("/etc/ufw/ufw.conf").read():
            fw = "ufw"
    except OSError:
        pass
    if not fw and shutil.which("firewall-cmd") and subprocess.run(["systemctl", "is-active", "-q", "firewalld"]).returncode == 0:
        fw = "firewalld"
    if fw:
        note(f"the {fw} firewall is on. If the phone says it can't reach the PC, allow port {API_PORT} from your home "
             f"network:\n      sudo ufw allow from 192.168.0.0/16 to any port {API_PORT} proto tcp" if fw == "ufw" else
             f"the firewalld firewall is on; port {API_PORT} must be open in your home zone")
    else:
        good("no firewall in the way")
    last = db.get("last_refresh") or {}
    n = db.q("SELECT COUNT(*) n FROM settlements WHERE deadline IS NULL OR deadline >= date('now')")[0]["n"]
    if last.get("at"):
        age = (time.time() - last["at"]) / 3600
        good(f"{n} open settlements, last checked {age:.0f} h ago") if age < 13 else \
            bad(f"settlements were last checked {age:.0f} h ago", "is the server running? try: claimscout refresh")
        for e in last.get("errors") or []:
            note(f"a source failed last time: {e[:160]}")
    else:
        note("the settlement sites haven't been checked yet (it starts when the server starts; or run: claimscout refresh)")
    from . import ai
    st = ai.public_settings(db)
    if st.get("provider", "off") == "off":
        good("AI is off (keyword matching). Optional: turn it on in the dashboard (claimscout open)")
    else:
        good(f"AI: {st.get('provider')} · {st.get('model') or 'no model set'}")
    print(f"\nPhone shows \"can't reach your PC\"? Same Wi-Fi as this PC (or Tailscale on both), then pair again with "
          f"`claimscout pair` if this PC's address changed ({', '.join(addrs)}).")


def main():
    ap = argparse.ArgumentParser(prog="claimscout")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("serve", help="run the phone API and the dashboard")
    s.add_argument("--port", type=int, default=API_PORT)
    s.add_argument("--web-port", type=int, default=WEB_PORT)
    sub.add_parser("refresh", help="pull settlements and score them now")
    pp = sub.add_parser("pair", help="print the pairing link and QR code for the phone")
    pp.add_argument("--qr-only", action="store_true", help=argparse.SUPPRESS)
    sub.add_parser("doctor", help="check why the phone can't connect, or anything else that looks wrong")
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
        if not a.qr_only:
            print(link)
        print("    Addresses in this code: " + ", ".join(pairing.addresses()) +
              ". Pairing again from the same PC keeps your data; `claimscout reset-token` unpairs every phone.")
    elif a.cmd == "doctor":
        doctor(db)
    elif a.cmd == "reset-token":
        pairing.reset_token(db)
        print("Every phone is unpaired. Run `claimscout pair` to pair again.")
    elif a.cmd == "open":
        webbrowser.open(f"http://127.0.0.1:{WEB_PORT}/#t={pairing.token(db)}")


if __name__ == "__main__":
    main()
