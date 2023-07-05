from galvo.controller import GalvoController

controller = GalvoController("default.json")
with controller as c:
    for i in range(200):
        c.dark(0x5000, 0x8000)
        c.light(0xA000, 0x8000)
        c.dark(0x8000, 0x5000)
        c.light(0x8000, 0xA000)
