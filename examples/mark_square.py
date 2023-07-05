from galvo.controller import GalvoController

controller = GalvoController("default.json")
with controller as c:
    c.goto(0x5000, 0x5000)
    c.mark(0x5000, 0xA000)
    c.mark(0xA000, 0xA000)
    c.mark(0x5000, 0xA000)
    c.mark(0x5000, 0x5000)
