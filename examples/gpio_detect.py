"""
Script toggles GPIO ports with keys between 0-f (hex).
Pressing escape quits.

Connection happens automatically at the first issue of realtime `write_port()` command.
"""

from galvo.controller import GalvoController
from pynput import keyboard

controller = GalvoController("default.json")


def toggle_gpio(key):
    if key == keyboard.Key.esc:
        return False  # Stop the keyboard listener
    try:
        char = key.char
    except AttributeError:
        return

    if char.lower() in "0123456789abcdef":
        bit = int(char, 16)
        if controller.is_port(bit):  # Check if the port is currently on
            controller.port_off(bit)  # Turn off the port
            print("Port", bit, "turned off")
        else:
            controller.port_on(bit)  # Turn on the port
            print("Port", bit, "turned on")
        controller.write_port()


print("Press keys [0-9, a-f] to toggle GPIO. Escape to exit.")

# Register the keyboard listener
keyboard_listener = keyboard.Listener(on_release=toggle_gpio)
keyboard_listener.start()

# Keep the main thread active until the listener is stopped
keyboard_listener.join()
