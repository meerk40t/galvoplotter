"""
Draws a circle in light with a radius that is updated with + and - key presses.
<space> causes the drawing to abort.
"""

import math
from pynput import keyboard
from galvo.controller import GalvoController

controller = GalvoController("default.json")

radius = 0x1000  # Initial radius
previous_radius = 0x1000


def draw_circle(c):
    """
    Draws a circle in light with a radius of radius.

    If the previous radius was different, we abort the previous drawn circles (that could still be in buffer) and
    draw the new radius.

    :param c:
    :return:
    """
    global radius
    global previous_radius
    if radius != previous_radius:
        previous_radius = radius
        c.abort()
    c.lighting_configuration()
    c.dark(0x8000, 0x9000)  # Move to the starting position
    for angle in range(0, 360, 10):
        x = 0x8000 + int(radius * math.cos(math.radians(angle)))
        y = 0x8000 + int(radius * math.sin(math.radians(angle)))
        c.light(x, y)
    c.dark(0x8000, 0x8000)  # Return to the center position
    return False


def on_release(key):
    global radius
    if key == keyboard.Key.space:
        controller.shutdown()
        return False
    try:
        char = key.char
    except AttributeError:
        return

    if char == "+":  # Check if "+" key is released
        radius += 0x100  # Increase the radius by a step
        print("Radius increased:", hex(radius))
    elif char == "-":  # Check if "-" key is released
        radius -= 0x100  # Decrease the radius by a step
        print("Radius decreased:", hex(radius))


listener = keyboard.Listener(on_release=on_release)
listener.start()

controller.submit(draw_circle)
print(radius)
