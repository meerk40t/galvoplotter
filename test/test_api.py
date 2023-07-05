import time
import unittest
from galvo import GalvoController

state = 0


class TestAPI(unittest.TestCase):
    def test_api_job(self):
        """
        Test submission of a test job.

        Test passes if the job quits out at around ~2 seconds.
        :return:
        """
        controller = GalvoController(settings_file="test.json")

        def my_job():
            """
            Never indicates job is finished.
            :return:
            """
            controller.light_mode()
            controller.dark(0x8000, 0x8000)
            controller.light(0x2000, 0x2000)
            return False

        controller.submit(my_job)
        time.sleep(2)
        controller.shutdown()

    def test_api_generator(self):
        """
        Test submission of a generator test job.

        Test passes if the job quits out at around ~2 seconds.

        :return:
        """

        controller = GalvoController(settings_file="test.json")

        def my_generator():
            while True:
                yield "dark", 0x8000, 0x8000
                yield "light", 0x2000, 0x2000

        controller.submit(controller.generate_job(my_generator))
        time.sleep(2)
        controller.shutdown()
