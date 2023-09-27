import os
import struct
import time
import unittest

from galvo import *

state = 0

__location__ = os.path.realpath(os.path.join(os.getcwd(), os.path.dirname(__file__)))

__settings__ = os.path.join(__location__, "test.json")


class TestSource(unittest.TestCase):
    def test_source_co2_power20_frequency10(self):
        c = GalvoController(settings_file=__settings__)
        old_send = c.send

        def test_send(data, read):
            if len(data) == 0xC00:
                words = [struct.unpack("<6H", data[i:i + 12]) for i in range(0, 0xC00, 0xC)]
                for c0, c1, c2, c3, c4, c5 in words:
                    if c0 == listMarkFreq:
                        self.assertEqual(c1, 0x03E8)
                    if c0 == listSetCo2FPK:
                        self.assertEqual(c1, 0x0C8)
                    if c0 == listMarkPowerRatio:
                        self.assertEqual(c1, 0x0190)
                    self.assertNotIn(c1, (listFiberYLPMPulseWidth, listQSwitchPeriod, listMarkCurrent))
            return old_send(data, read)

        c.send = test_send

        c.source = "co2"
        c.power = 20
        c.frequency = 10
        c.fpk = 10.0
        c.set()
        with c.marking():
            c.goto(0x5000, 0x5000)
            c.mark(0x5000, 0xA000)
        c.wait_for_machine_idle()

    def test_source_co2_power30_frequency20(self):
        c = GalvoController(settings_file=__settings__)
        old_send = c.send

        def test_send(data, read):
            if len(data) == 0xC00:
                words = [struct.unpack("<6H", data[i:i + 12]) for i in range(0, 0xC00, 0xC)]
                for c0, c1, c2, c3, c4, c5 in words:
                    if c0 == listMarkFreq:
                        self.assertEqual(c1, 0x01F4)
                    if c0 == listSetCo2FPK:
                        self.assertEqual(c1, 0x0064)
                    if c0 == listMarkPowerRatio:
                        self.assertEqual(c1, 0x012C)
                    self.assertNotIn(c1, (listFiberYLPMPulseWidth, listQSwitchPeriod, listMarkCurrent))
            return old_send(data, read)

        c.send = test_send

        c.source = "co2"
        c.power = 30
        c.frequency = 20
        c.fpk = 10.0
        c.set()
        with c.marking():
            c.goto(0x5000, 0x5000)
            c.mark(0x5000, 0xA000)
        c.wait_for_machine_idle()

    def test_source_co2_power40_frequency30(self):
        c = GalvoController(settings_file=__settings__)
        old_send = c.send

        def test_send(data, read):
            if len(data) == 0xC00:
                words = [struct.unpack("<6H", data[i:i + 12]) for i in range(0, 0xC00, 0xC)]
                for c0, c1, c2, c3, c4, c5 in words:
                    if c0 == listMarkFreq:
                        self.assertEqual(c1, 0x014D)
                    if c0 == listSetCo2FPK:
                        self.assertEqual(c1, 0x0043)
                    if c0 == listMarkPowerRatio:
                        self.assertEqual(c1, 0x010B)
                    self.assertNotIn(c1, (listFiberYLPMPulseWidth, listQSwitchPeriod, listMarkCurrent))
            return old_send(data, read)

        c.send = test_send

        c.source = "co2"
        c.power = 40
        c.frequency = 30
        c.fpk = 10.0
        c.set()
        with c.marking():
            c.goto(0x5000, 0x5000)
            c.mark(0x5000, 0xA000)
        c.wait_for_machine_idle()

    def test_source_co2_power50_frequency80(self):
        c = GalvoController(settings_file=__settings__)
        old_send = c.send

        def test_send(data, read):
            if len(data) == 0xC00:
                words = [struct.unpack("<6H", data[i:i + 12]) for i in range(0, 0xC00, 0xC)]
                for c0, c1, c2, c3, c4, c5 in words:
                    if c0 == listMarkFreq:
                        self.assertEqual(c1, 0x007D)
                    if c0 == listSetCo2FPK:
                        self.assertEqual(c1, 0x0019)
                    if c0 == listMarkPowerRatio:
                        self.assertEqual(c1, 0x007D)
                    self.assertNotIn(c1, (listFiberYLPMPulseWidth, listQSwitchPeriod, listMarkCurrent))
            return old_send(data, read)

        c.send = test_send

        c.source = "co2"
        c.set(power=50, frequency=80.0, fpk=10.0)
        with c.marking():
            c.goto(0x5000, 0x5000)
            c.mark(0x5000, 0xA000)
        c.wait_for_machine_idle()
