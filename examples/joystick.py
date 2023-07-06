"""
Requires: pygame
Hardware: Joystick

Script will allow you to control the laser with a joystick/d-pad. Button 0 will fire the laser for 100ms at the current
location.
"""

import pygame

from galvo.controller import GalvoController

controller = GalvoController("default.json")


def fire_at_position(x: int, y: int, time_in_ms: float = 100):
    """
    Reusable command. Fires at position x,y for the given amount of time.
    :param x: x position to fire at.
    :param y: y position to fire at.
    :param time_in_ms: time to fire for.
    :return:
    """

    def func(m):
        with m.marking():
            m.goto(x, y)
            m.dwell(time_in_ms)
            return True

    return func


def main():
    pygame.init()
    pygame.joystick.init()

    if pygame.joystick.get_count() == 0:
        print("No joystick found.")
        return

    joystick = pygame.joystick.Joystick(0)
    joystick.init()

    try:
        controller.light_on()
        controller.write_port()

        while True:
            pygame.event.get()
            x_axis = int((joystick.get_axis(0) + 1) * 0xFFFF / 2)
            y_axis = int((joystick.get_axis(1) + 1) * 0xFFFF / 2)
            # Read joystick buttons
            fire_button = joystick.get_button(0)
            print("X-axis: {:04X}  Y-axis: {:04X}".format(x_axis, y_axis))
            controller.jog(x_axis, y_axis)
            if fire_button:
                controller.submit(fire_at_position(x_axis, y_axis))
                controller.wait_for_machine_idle()
    except KeyboardInterrupt:
        joystick.quit()


if __name__ == "__main__":
    main()
