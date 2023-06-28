import pygame

from galvo.controller import GalvoController

controller = GalvoController("../default.json")


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
        while True:
            pygame.event.get()
            x_axis = int((joystick.get_axis(0) + 1) * 0xFFFF / 2)
            y_axis = int((joystick.get_axis(1) + 1) * 0xFFFF / 2)
            # Read joystick buttons
            fire_button = joystick.get_button(0)
            print("X-axis: {:04X}  Y-axis: {:04X}".format(x_axis, y_axis))
            controller.goto_xy(x_axis, y_axis)
            if fire_button:
                controller.program_mode()
                controller.goto(x_axis, y_axis)
                dwell_time = 100
                controller.list_laser_on_point(dwell_time * 100)
                controller.rapid_mode()
    except KeyboardInterrupt:
        joystick.quit()


if __name__ == "__main__":
    main()