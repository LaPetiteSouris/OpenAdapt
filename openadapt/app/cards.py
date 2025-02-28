"""openadapt.app.cards module.

This module provides functions for managing UI cards in the OpenAdapt application.
"""

from subprocess import Popen
import signal

from nicegui import ui

from openadapt.app.objects.local_file_picker import LocalFilePicker
from openadapt.app.util import set_dark, sync_switch

PROC = None


def settings(dark_mode: bool) -> None:
    """Display the settings dialog.

    Args:
        dark_mode (bool): Current dark mode setting.
    """
    with ui.dialog() as settings, ui.card():
        s = ui.switch(
            "Dark mode",
            on_change=lambda: set_dark(dark_mode, s.value),
        )
        sync_switch(s, dark_mode)
        ui.button("Close", on_click=lambda: settings.close())

    settings.open()


def select_import(f: callable) -> None:
    """Display the import file selection dialog.

    Args:
        f (callable): Function to call when import button is clicked.
    """

    async def pick_file() -> None:
        result = await LocalFilePicker(".")
        ui.notify(f"Selected {result[0]}" if result else "No file selected.")
        selected_file.text = result[0] if result else ""
        import_button.enabled = True if result else False

    with ui.dialog() as import_dialog, ui.card():
        with ui.column():
            ui.button("Select File", on_click=pick_file).props("icon=folder")
            selected_file = ui.label("")
            selected_file.visible = False
            import_button = ui.button(
                "Import",
                on_click=lambda: f(selected_file.text, delete.value),
            )
            import_button.enabled = False
            delete = ui.checkbox("Delete file after import")

    import_dialog.open()


def recording_prompt(options: list[str], record_button: ui.button) -> None:
    """Display the recording prompt dialog.

    Args:
        options (list): List of autocomplete options.
        record_button (nicegui.widgets.Button): Record button widget.
    """
    if PROC is None:
        with ui.dialog() as dialog, ui.card():
            ui.label("Enter a name for the recording: ")
            ui.input(
                label="Name",
                placeholder="test",
                autocomplete=options,
                on_change=lambda e: result.set_text(e),
            )
            result = ui.label()

            with ui.row():
                ui.button("Close", on_click=dialog.close)
                ui.button("Enter", on_click=lambda: on_record())

            dialog.open()

    def terminate() -> None:
        global process
        process.send_signal(signal.SIGINT)

        # Wait for process to terminate
        process.wait()
        ui.notify("Stopped recording")
        record_button._props["name"] = "radio_button_checked"
        record_button.on("click", lambda: recording_prompt(options, record_button))

        process = None

    def begin() -> None:
        name = result.text.__getattribute__("value")

        ui.notify(f"Recording {name}... Press CTRL + C in terminal window to cancel")
        PROC = Popen("python3 -m openadapt.record " + name, shell=True)
        record_button._props["name"] = "stop"
        record_button.on("click", lambda: terminate())
        record_button.update()
        return PROC

    def on_record() -> None:
        global PROC
        dialog.close()
        PROC = begin()
