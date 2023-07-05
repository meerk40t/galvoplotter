from galvo.controller import GalvoController

controller = GalvoController("default.json")
with controller as c:
    for x in range(0x1000, 0xFFFF, 0x1000):
        for y in range(0x1000, 0xFFFF, 0x1000):
            c.dark(x, y)
            c.light_on()
            c.list_write_port()
            delay_time_in_ms = 500
            c.list_delay_time(delay_time_in_ms * 100)  # 10-microseconds units to ms units is factor of 100
