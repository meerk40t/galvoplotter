import time
import unittest
from galvo import GalvoController, generate_job

state = 0


class TestAPI(unittest.TestCase):
    def test_api_job(self):
        """
        Test submission of a test job.

        Test passes if the job quits out at around ~2 seconds.
        :return:
        """
        controller = GalvoController(settings_file="test.json")

        def my_job(c):
            """
            Never indicates job is finished.
            :return:
            """
            c.lighting_configuration()
            c.dark(0x8000, 0x8000)
            c.light(0x2000, 0x2000)
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

        controller.submit(generate_job(my_generator))
        time.sleep(2)
        controller.shutdown()

    def test_api_wait(self):
        """
        Test wait command for api.

        Test passes if job quits after finish with print as last element.
        :return:
        """
        controller = GalvoController(settings_file="test.json")
        controller.count = 0

        def my_job(c):
            """
            Never indicates job is finished.
            :return:
            """
            if c.count > 1000:
                return True
            c.count += 1
            c.lighting_configuration()
            c.dark(0x8000, 0x8000)
            c.light(0x2000, 0x2000)
            return False

        controller.submit(my_job)
        controller.wait_for_machine_idle()
        print("final line...")

    def test_mark_square(self):
        c = GalvoController(settings_file="test.json")
        c.marking_configuration()
        c.goto(0x5000, 0x5000)
        c.mark(0x5000, 0xA000)
        c.mark(0xA000, 0xA000)
        c.mark(0x5000, 0xA000)
        c.mark(0x5000, 0x5000)
        c.initial_configuration()
        c.wait_for_machine_idle()
        print("final line...")