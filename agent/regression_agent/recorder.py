"""Console/network event recording, scoped per navigation step.

A single Recorder is attached to a page for the lifetime of a crawl. Each
flow step calls `mark()` before acting and `since(mark)` after, so evidence
is naturally bucketed per step instead of one undifferentiated stream.
"""


class Recorder:
    def __init__(self, page):
        self.console = []  # list of {"kind": str, "text": str}
        self.network = []  # list of {"url": str, "method": str, "status": int}
        page.on("console", self._on_console)
        page.on("pageerror", self._on_pageerror)
        page.on("response", self._on_response)

    def _on_console(self, msg):
        if msg.type in ("error", "warning"):
            self.console.append({"kind": msg.type, "text": msg.text})

    def _on_pageerror(self, exc):
        self.console.append({"kind": "pageerror", "text": str(exc)})

    def _on_response(self, response):
        try:
            self.network.append({
                "url": response.url,
                "method": response.request.method,
                "status": response.status,
            })
        except Exception:
            pass

    def mark(self):
        return (len(self.console), len(self.network))

    def since(self, mark):
        c_idx, n_idx = mark
        return list(self.console[c_idx:]), list(self.network[n_idx:])
