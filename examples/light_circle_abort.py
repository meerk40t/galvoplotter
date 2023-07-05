import math
from pynput import keyboard
from galvo.controller import GalvoController

controller = GalvoController("default.json")

radius = 0x1000  # Initial radius


def draw_circle():
    with controller.lighting() as c:
        c.dark(0x8000, 0x9000)  # Move to the starting position
        for angle in range(0, 360, 10):
            global radius
            x = 0x8000 + int(radius * math.cos(math.radians(angle)))
            y = 0x8000 + int(radius * math.sin(math.radians(angle)))
            c.light(x, y)
        c.dark(0x8000, 0x8000)  # Return to the center position


def on_release(key):
    global radius
    if key == keyboard.Key.space:
        controller.abort()
        controller.shutdown()
        return False
    try:
        char = key.char
    except AttributeError:
        return

    if char == "+":  # Check if "+" key is released
        radius += 0x100  # Increase the radius by a step
        print("Radius increased:", hex(radius))
        controller.abort()
    elif char == "-":  # Check if "-" key is released
        radius -= 0x100  # Decrease the radius by a step
        print("Radius decreased:", hex(radius))
        controller.abort()


listener = keyboard.Listener(on_release=on_release)
listener.start()

controller.submit(draw_circle)
print(radius)
