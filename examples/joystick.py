"""
Requires: pygame
Hardware: Joystick

Script will allow you to control the laser with a joystick/d-pad. Button 0 will fire the laser for 100ms at the current
location.
"""

import pygame

from galvo.controller import GalvoController

controller = GalvoController("default.json")


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
            controller.goto_xy(x_axis, y_axis)
            if fire_button:
                def fire_at_xy():
                    with controller.marking() as m:
                        m.goto(x_axis, y_axis)
                        m.dwell(100)
                    return True

                controller.submit(fire_at_xy)
    except KeyboardInterrupt:
        joystick.quit()


if __name__ == "__main__":
    main()