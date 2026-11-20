# -*- coding: utf-8 -*-
# GNU General Public License v3.0+ (see LICENSES/GPL-3.0-or-later.txt or https://www.gnu.org/licenses/gpl-3.0.txt)
"""Tiny SMTP sink for testing report e-mail delivery without a real mail server.

Accepts any sender/recipient (no auth, no TLS) and writes each received message to
OUTPUT_DIR/message-<n>.eml, then keeps listening.

    python3 tests/e2e/smtp_sink.py --port 2525 --output /tmp/smtp-sink
    ansible-playbook docs/examples/deliver_reports.yml -e @tests/e2e/vars.yml \\
      -e report_mail_to=you@example.com -e report_smtp_host=127.0.0.1 -e report_smtp_port=2525
"""

from __future__ import absolute_import, division, print_function

__metaclass__ = type

import argparse
import os
import socketserver


class SinkHandler(socketserver.StreamRequestHandler):
    output_dir = "."
    counter = 0

    def reply(self, text):
        self.wfile.write((text + "\r\n").encode("utf-8"))

    def handle(self):
        self.reply("220 smtp-sink ESMTP ready")
        lines, in_data = [], False
        for raw in self.rfile:
            line = raw.decode("utf-8", errors="replace").rstrip("\r\n")
            if in_data:
                if line == ".":
                    self.save(lines)
                    lines, in_data = [], False
                    self.reply("250 OK queued")
                else:
                    lines.append(line[1:] if line.startswith("..") else line)  # undo dot-stuffing
                continue
            verb = line[:4].upper()
            if verb == "EHLO":
                self.wfile.write(b"250-smtp-sink\r\n250 SIZE 52428800\r\n")
            elif verb == "HELO":
                self.reply("250 smtp-sink")
            elif verb == "DATA":
                in_data = True
                self.reply("354 End data with <CR><LF>.<CR><LF>")
            elif verb == "QUIT":
                self.reply("221 Bye")
                return
            else:  # MAIL FROM, RCPT TO, RSET, NOOP, ...
                self.reply("250 OK")

    def save(self, lines):
        SinkHandler.counter += 1
        path = os.path.join(self.output_dir, "message-%d.eml" % SinkHandler.counter)
        with open(path, "w") as handle:
            handle.write("\n".join(lines) + "\n")
        print("saved %s" % path, flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--port", type=int, default=2525)
    parser.add_argument("--bind", default="127.0.0.1")
    parser.add_argument("--output", default=".", help="directory for received .eml files")
    args = parser.parse_args()
    os.makedirs(args.output, exist_ok=True)
    SinkHandler.output_dir = args.output
    socketserver.TCPServer.allow_reuse_address = True
    server = socketserver.TCPServer((args.bind, args.port), SinkHandler)
    print("smtp sink on %s:%d, saving to %s" % (args.bind, args.port, args.output), flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
