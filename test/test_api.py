import time
import unittest
from galvo import GalvoController, generate_job

state = 0



def infinite_lighting_job(c):
    """
    Never indicates job is finished.
    :return:
    """
    c.lighting_configuration()
    c.dark(0x8000, 0x8000)
    c.light(0x2000, 0x2000)
    return False


def infinite_marking_job(c):
    """
    Never indicates job is finished.
    :return:
    """
    c.marking_configuration()
    c.goto(0x8000, 0x8000)
    c.mark(0x2000, 0x2000)
    return False


class TestAPI(unittest.TestCase):
    def test_api_shutdown_job(self):
        """
        Test submission of a test job with shutdown.

        Test passes if the job quits out at around ~2 seconds.
        :return:
        """
        controller = GalvoController(settings_file="test.json")
        controller.submit(infinite_lighting_job)
        time.sleep(2)
        controller.shutdown()

    def test_api_cancel_job(self):
        """
        Test submission of a test job with removal

        Test passes if the job quits out at around ~2 seconds.
        :return:
        """
        controller = GalvoController(settings_file="test.json")
        controller.submit(infinite_lighting_job)
        time.sleep(2)
        controller.remove(infinite_lighting_job)

    def test_api_cancel_2job(self):
        """
        Test submission of two jobs. One an infinite lighting job, one an infinite marking job. Cancel sequentially.

        Test passes if the job quits out at around ~4 seconds.
        :return:
        """
        controller = GalvoController(settings_file="test.json")
        controller.submit(infinite_lighting_job)
        controller.submit(infinite_marking_job)
        time.sleep(2)
        self.assertIs(controller.current, infinite_lighting_job)
        controller.remove(infinite_lighting_job)
        time.sleep(2)
        self.assertIs(controller.current, infinite_marking_job)
        controller.remove(infinite_marking_job)

    def test_api_pause(self):
        """
        Starts a lighting job. After two seconds pauses. Resumes after 4 more seconds. Cancels after 2 more seconds.

        Test passes if the job quits out at around ~8 seconds (with paused execution).
        :return:
        """
        controller = GalvoController(settings_file="test.json")
        controller.submit(infinite_lighting_job)
        time.sleep(2)
        self.assertIs(controller.current, infinite_lighting_job)
        controller.pause()
        print("Paused for four seconds.")
        time.sleep(4)
        self.assertIs(controller.current, infinite_lighting_job)
        controller.resume()
        print("Resumed")
        time.sleep(2)
        controller.remove(infinite_lighting_job)


    def test_api_generator(self):
        """
        Test submission of a generator test job, with shutdown.

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
            if c.count > 1000:
                return True
            c.count += 1
            c.lighting_configuration()
            c.dark(0x8000, 0x8000)
            c.light(0x2000, 0x2000)
            return False

        controller.submit(my_job)
        controller.wait_for_machine_idle()
        print("test_api_wait: final line or test fail")

    def test_mark_square(self):
        """
        Test for marking a simple square.
        :return:
        """
        c = GalvoController(settings_file="test.json")
        with c.marking():
            c.goto(0x5000, 0x5000)
            c.mark(0x5000, 0xA000)
            c.mark(0xA000, 0xA000)
            c.mark(0x5000, 0xA000)
            c.mark(0x5000, 0x5000)
        c.wait_for_machine_idle()
        print("test_mark_square: final line or test fail.")

    def test_grid_stops(self):
        """
        Test for a grid of lit points.
        :return:
        """
        controller = GalvoController(settings_file="test.json")
        with controller.lighting() as c:
            for x in range(0x1000, 0xFFFF, 0x1000):
                for y in range(0x1000, 0xFFFF, 0x1000):
                    c.dark(x, y)
                    c.light_on()
                    c.wait(500)
        controller.wait_for_machine_idle()
