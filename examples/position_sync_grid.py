from galvo.controller import GalvoController

controller = GalvoController("default.json")
with controller.lighting() as c:
    for x in range(0x1000, 0xFFFF, 0x1000):
        for y in range(0x1000, 0xFFFF, 0x1000):
            c.dark(x, y)
            if c.light_on():
                c.list_write_port()
            c.wait(500)
