"""A tiny local mail server for trying out sharing and reminders without a real mail account.

    python scripts/smtp_sink.py --port 1025 --out sent_mail

Start the backend with   SMTP_HOST=127.0.0.1  SMTP_PORT=1025  SMTP_TLS=false
Every message it receives is saved as a .eml file in the --out folder (open it with a mail
program) and printed as one line. It never forwards anything.
"""
import argparse
import asyncio
import itertools
from email import message_from_bytes
from pathlib import Path

counter = itertools.count(1)


async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter, out: Path) -> None:
    async def say(line: str) -> None:
        writer.write((line + "\r\n").encode())
        await writer.drain()

    await say("220 smtp-sink ready")
    recipients: list[str] = []
    while True:
        raw = await reader.readline()
        if not raw:
            break
        cmd = raw.decode(errors="replace").strip()
        upper = cmd.upper()
        if upper.startswith(("EHLO", "HELO")):
            await say("250 smtp-sink")
        elif upper.startswith("MAIL FROM"):
            recipients = []
            await say("250 OK")
        elif upper.startswith("RCPT TO"):
            recipients.append(cmd.split(":", 1)[1].strip())
            await say("250 OK")
        elif upper == "DATA":
            await say("354 End data with <CR><LF>.<CR><LF>")
            body = b""
            while True:
                line = await reader.readline()
                if line in (b".\r\n", b""):
                    break
                body += line[1:] if line.startswith(b"..") else line
            path = out / f"mail_{next(counter):03d}.eml"
            path.write_bytes(body)
            msg = message_from_bytes(body)
            attachments = [p.get_filename() for p in msg.walk() if p.get_filename()]
            print(f"saved {path.name}: to={msg['To']} subject={msg['Subject']!r} attachments={attachments}", flush=True)
            await say("250 OK message saved")
        elif upper == "QUIT":
            await say("221 bye")
            break
        elif upper == "RSET" or upper == "NOOP":
            await say("250 OK")
        else:
            await say("502 command not supported")
    writer.close()


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--port", type=int, default=1025)
    parser.add_argument("--out", default="sent_mail")
    args = parser.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    server = await asyncio.start_server(lambda r, w: handle(r, w, out), "127.0.0.1", args.port)
    print(f"smtp-sink listening on 127.0.0.1:{args.port}, saving mail to {out.resolve()}", flush=True)
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
