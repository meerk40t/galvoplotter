import time
import unittest

state = 0


class TestAPI(unittest.TestCase):
    def test_api(self):
        from galvo import GalvoController

        controller = GalvoController(settings_file="test.json")

        def my_command():
            controller.dark(0x8000, 0x8000)
            controller.light(0x2000, 0x2000)
            return False

        controller.submit(my_command)
        time.sleep(2)
        controller.shutdown()
