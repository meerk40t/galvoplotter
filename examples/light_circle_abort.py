import threading
import math
from pynput import keyboard
from galvo.controller import GalvoController

controller = GalvoController("../default.json")

radius = 0x1000  # Initial radius


def draw_circle():
    global radius
    with controller as c:
        c.goto(0x8000, 0x9000)  # Move to the starting position

        while not controller.is_shutdown:
            for angle in range(0, 360, 10):
                x = 0x8000 + int(radius * math.cos(math.radians(angle)))
                y = 0x8000 + int(radius * math.sin(math.radians(angle)))
                c.light(x, y)

        c.goto(0x8000, 0x8000)  # Return to the center position


def on_release(key):
    global radius
    if key == keyboard.Key.space:
        controller.abort()
        controller.shutdown()
        return False
    elif key.char == "+":  # Check if "+" key is released
        radius += 0x100  # Increase the radius by a step
        print("Radius increased:", hex(radius))
    elif key.char == "-":  # Check if "-" key is released
        radius -= 0x100  # Decrease the radius by a step
        print("Radius decreased:", hex(radius))


listener = keyboard.Listener(on_release=on_release)
listener.start()

# Start the circle-drawing process in a separate thread
drawing_thread = threading.Thread(target=draw_circle)
drawing_thread.start()
drawing_thread.join()

print(radius)
