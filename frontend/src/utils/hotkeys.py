# frontend/src/utils/hotkeys.py

from pynput import keyboard

class HotkeyManager:
    """
    Listens for global key events and calls the provided callback
    with (key, event_type) where event_type is 'down' or 'up'.
    """
    def __init__(self, callback):
        self.callback = callback

    def start_listening(self):
        def on_press(key):
            try:
                self.callback(key, 'down')
            except Exception:
                pass

        def on_release(key):
            try:
                self.callback(key, 'up')
            except Exception:
                pass

        listener = keyboard.Listener(on_press=on_press, on_release=on_release)
        listener.start()
