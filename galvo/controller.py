"""
Galvo Controller

The balor controller takes low level lmc galvo commands and converts them into lists and shorts commands to send
to the hardware controller.
"""

import struct
import threading
import time
from copy import copy
from .consts import *

from .mock_connection import MockConnection
from .usb_connection import USBConnection


BUSY = 0x04
READY = 0x20

nop = [0x02, 0x80, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
empty = bytearray(nop * 0x100)


class GalvoController:
    """
    Galvo controller is tasked with sending queued data to the controller board and ensuring that the connection to the
    controller board is established to perform these actions.

    This should serve as a next generation command sequencer written from scratch for galvo lasers. The goal is to
    provide all the given commands in a coherent queue structure which provides correct sequences between list and
    single commands.
    """

    def __init__(
        self,
        settings_file=None,
        x=0x8000,
        y=0x8000,
        mark_speed=100.0,
        travel_speed=2000.0,
        power=50.0,
        frequency=30.0,
        goto_speed=None,
        light_speed=None,
        dark_speed=None,
        pulse_width=None,  # 4 is a typical default.
        light_pin=8,
        foot_pin=15,
        galvos_per_mm=500,
        cor_file=None,
        first_pulse_killer=200,
        pwm_pulse_width=125,
        pwm_half_period=125,
        standby_p1=2000,
        standby_p2=20,
        timing_mode=1,
        delay_mode=1,
        laser_mode=1,
        control_mode=0,
        fpk2_max_voltage=0xFFB,
        fpk2_min_voltage=1,
        fpk2_t1=409,
        fpk2_t2=100,
        fly_resolution_1=0,
        fly_resolution_2=99,
        fly_resolution_3=1000,
        fly_resolution_4=25,
        delay_laser_on=100.0,
        delay_laser_off=100.0,
        delay_polygon=100.0,
        delay_end=300.0,
        delay_open_mo=8.0,
        delay_jump_short=8,
        delay_jump_long=200.0,
        input_passes_required=3,
        mock=False,
        machine_index=0,
        usb_log=None,
    ):
        self._shutdown = False
        self._sending = True

        self._spooler_lock = threading.Condition()
        self._queue = []
        self._current = None
        self._spooler_thread = None

        self._list_build_lock = threading.RLock()
        self.mock = mock
        self.connection = None
        self.light_pin = light_pin
        self.footpedal_pin = foot_pin
        self.laser_pin = 0
        self.galvos_per_mm = galvos_per_mm

        self.mark_speed = mark_speed
        self.travel_speed = travel_speed
        self.power = power
        self.frequency = frequency

        self.cor_file = cor_file
        self.first_pulse_killer = first_pulse_killer
        self.pwm_pulse_width = pwm_pulse_width
        self.pwm_half_period = pwm_half_period
        self.standby_param_1 = standby_p1
        self.standby_param_2 = standby_p2
        self.timing_mode = timing_mode
        self.delay_mode = delay_mode
        self.laser_mode = laser_mode
        self.control_mode = control_mode
        self.fpk_max_voltage = fpk2_max_voltage
        self.fpk_min_voltage = fpk2_min_voltage
        self.fpk_t1 = fpk2_t1
        self.fpk_t2 = fpk2_t2
        self.fly_resolution_1 = fly_resolution_1
        self.fly_resolution_2 = fly_resolution_2
        self.fly_resolution_3 = fly_resolution_3
        self.fly_resolution_4 = fly_resolution_4
        self.input_passes_required = input_passes_required

        self.pulse_width = pulse_width

        self.delay_laser_on = delay_laser_on
        self.delay_laser_off = delay_laser_off
        self.delay_polygon = delay_polygon
        self.delay_end = delay_end
        self.delay_open_mo = delay_open_mo
        self.delay_jump_short = delay_jump_short
        self.delay_jump_long = delay_jump_long

        # Running attributes
        self._usb_log = usb_log
        self._is_connecting_to_laser = False
        self._abort_open = False
        self._disable_connect = False

        self._port_bits = 0
        self._machine_index = machine_index
        self.laser_configuration = "initial"
        self._active_list = None
        self._active_index = 0
        self._list_executing = False
        self._number_of_list_packets = 0
        self.paused = False

        # Set attributes, these are actively sent to the controller already.
        self._last_x = x
        self._last_y = y
        self._mark_speed = mark_speed
        self._goto_speed = goto_speed
        self._light_speed = light_speed
        self._dark_speed = dark_speed

        self._ready = None
        self._speed = None
        self._travel_speed = None
        self._frequency = None
        self._power = None
        self._pulse_width = None

        self._delay_jump = None
        self._delay_on = None
        self._delay_off = None
        self._delay_poly = None
        self._delay_end = None
        if settings_file is not None:
            import json
            with open(settings_file, 'r') as fp:
                self.__dict__.update(json.load(fp))

    #######################
    # SPOOLER MANAGEMENT
    #######################

    def submit(self, job):
        with self._spooler_lock:
            self._queue.append(job)
            self._spooler_lock.notify_all()
        self.start()

    def remove(self, element):
        with self._spooler_lock:
            for i in range(len(self._queue) - 1, -1, -1):
                e = self._queue[i]
                if e is element:
                    del self._queue[i]
            self._spooler_lock.notify_all()

    def shutdown(self, *args, **kwargs):
        self._shutdown = True
        with self._spooler_lock:
            try:
                # If something is currently processing stop it.
                self._current.stop()
            except AttributeError:
                pass
            self._spooler_lock.notify_all()
            self._queue.clear()
            self.abort()
        if self._spooler_thread:
            self._spooler_thread.join()

    def start(self):
        self._shutdown = False
        if not self._spooler_thread:
            self._spooler_thread = threading.Thread(target=self._spooler_run)
            self._spooler_thread.start()

    def _spooler_run(self):
        """
        Spooler run thread. While the controller is not shutdown we read the queue and execute whatever functions are
        located in the queue. The jobs return whether they were fully_executed. If they were they are removed
        as completed and the next item in queue is processed.

        :return:
        """
        while not self._shutdown:
            with self._spooler_lock:
                try:
                    program = self._queue[0]
                except IndexError:
                    if self._shutdown:
                        return
                    # There is no work to do.
                    self._spooler_lock.wait()
                    continue
            self._current = program
            if self._shutdown:
                return
            try:
                fully_executed = program(self)
            except ConnectionAbortedError:
                # Driver could no longer connect to where it was told to send the data.
                return
            except ConnectionRefusedError:
                # Driver connection failed but, we are not giving up.
                if self._shutdown:
                    return
                with self._spooler_lock:
                    self._spooler_lock.wait()
                continue
            if fully_executed:
                # all work finished
                self.remove(program)

    @property
    def current(self):
        return self._current

    @property
    def queue(self):
        return self._queue

    def usb_log(self, data):
        if self._usb_log:
            self._usb_log(data)

    @property
    def state(self):
        if self.laser_configuration == "initial":
            return "idle", "idle"
        if self.paused:
            return "hold", "paused"
        if self.laser_configuration == "lighting":
            return "busy", "lighting"
        if self.laser_configuration == "marking":
            return "busy", "marking"

    #######################
    # Connection Handler
    #######################

    @property
    def is_connected(self):
        """
        Check whether the controller state is connected to the laser.
        :return:
        """
        if self.connection is None:
            return False
        return self.connection.is_open(self._machine_index)

    @property
    def is_connecting(self):
        """
        Check whether the controller state is current connecting (but not yet connected) to the laser.
        :return:
        """
        if self.connection is None:
            return False
        return self._is_connecting_to_laser

    @property
    def is_connection_allowed(self):
        """
        Check whether the controller state currently allows connection attempts.

        To clear this state requires calling `disconnect()` directly. The connection failed and all commands should
        issue a `ConnectionRefusedError`.
        :return:
        """
        return not self._disable_connect

    @property
    def is_executing(self):
        """
        Check whether the controller is executing a list-command queue. This should be true anytime the queue is not
        empty or not fully executed.
        :return:
        """
        return self.can_spool and len(self._queue)

    @property
    def can_spool(self):
        """
        Check whether the controller is accepting job submissions. This should be true for most of the lifecycle except
        after and during shutdown.
        :return:
        """
        return not self._shutdown

    def abort_connect(self):
        self._abort_open = True
        self.usb_log("Connect Attempts Aborted")

    def disconnect(self):
        try:
            self.connection.close(self._machine_index)
        except (ConnectionError, ConnectionRefusedError, AttributeError):
            pass
        self.connection = None
        # Reset error to allow another attempt
        self._disable_connect = False

    def connect_if_needed(self):
        if self._disable_connect:
            # After many failures automatic connects are disabled. We require a manual connection.
            self.abort_connect()
            self.connection = None
            raise ConnectionRefusedError(
                "LMC was unreachable. Explicit connect required."
            )
        if self.connection is None:
            if self.mock:
                self.connection = MockConnection(self.usb_log)
                self.connection.send = print
                self.connection.recv = print
            else:
                self.connection = USBConnection(self.usb_log)
        self._is_connecting_to_laser = True
        self._abort_open = False
        count = 0
        while not self.connection.is_open(self._machine_index):
            try:
                if self.connection.open(self._machine_index) < 0:
                    raise ConnectionError
                self.init_laser()
            except (ConnectionError, ConnectionRefusedError):
                time.sleep(0.3)
                count += 1
                if not self._sending or self._abort_open:
                    self._is_connecting_to_laser = False
                    self._abort_open = False
                    return
                if self.connection.is_open(self._machine_index):
                    self.connection.close(self._machine_index)
                if count >= 10:
                    # We have failed too many times.
                    self._is_connecting_to_laser = False
                    self._disable_connect = True
                    self.usb_log("Could not connect to the LMC controller.")
                    self.usb_log("Automatic connections disabled.")
                    raise ConnectionRefusedError(
                        "Could not connect to the LMC controller."
                    )
                time.sleep(0.3)
                continue
        self._is_connecting_to_laser = False
        self._abort_open = False

    def send(self, data, read=True):
        if not self._sending:
            return -1, -1, -1, -1
        self.connect_if_needed()
        try:
            self.connection.write(self._machine_index, data)
        except ConnectionError:
            return -1, -1, -1, -1
        if read:
            try:
                r = self.connection.read(self._machine_index)
                return struct.unpack("<4H", r)
            except ConnectionError:
                return -1, -1, -1, -1

    def status(self):
        b0, b1, b2, b3 = self.get_version()
        return b3

    #######################
    # MODE SHIFTS
    #######################

    def initial_configuration(self):
        if self.laser_configuration == "initial":
            return
        self.list_end_of_list()  # Ensure at least one list_end_of_list
        self._list_end()
        if not self._list_executing and self._number_of_list_packets:
            # If we never ran the list, and we sent some lists.
            self.execute_list()
        self._list_executing = False
        self._number_of_list_packets = 0
        self.wait_idle()
        self.set_fiber_mo(0)
        self.port_off(bit=self.laser_pin)
        self.write_port()
        marktime = self.get_mark_time()
        self.usb_log(f"Time taken for list execution: {marktime}")
        self.laser_configuration = "initial"

    def marking_configuration(self):
        if self.laser_configuration == "marking":
            return
        if self.laser_configuration == "lighting":
            self.laser_configuration = "marking"
            self.light_off()
            self.port_on(bit=self.laser_pin)
            self.write_port()
            self.set_fiber_mo(1)
        else:
            self.laser_configuration = "marking"
            self.reset_list()
            self.port_on(bit=self.laser_pin)
            self.write_port()
            self.set_fiber_mo(1)
            self._ready = None
            self._speed = None
            self._travel_speed = None
            self._frequency = None
            self._power = None
            self._pulse_width = None

            self._delay_jump = None
            self._delay_on = None
            self._delay_off = None
            self._delay_poly = None
            self._delay_end = None
            self.list_ready()
            if self.delay_open_mo:
                self.list_delay_time(int(self.delay_open_mo * 100))
            self.list_write_port()
        self.set()

    def lighting_configuration(self):
        if self.laser_configuration == "lighting":
            return
        if self.laser_configuration == "marking":
            self.set_fiber_mo(0)
            self.port_off(self.laser_pin)
            self.port_on(self.light_pin)
            self.write_port()
        else:
            self._ready = None
            self._speed = None
            self._travel_speed = None
            self._frequency = None
            self._power = None
            self._pulse_width = None

            self._delay_jump = None
            self._delay_on = None
            self._delay_off = None
            self._delay_poly = None
            self._delay_end = None

            self.reset_list()
            self.list_ready()
            self.port_off(self.laser_pin)
            self.port_on(self.light_pin)
            self.list_write_port()
        self.laser_configuration = "lighting"

    #######################
    # PLOTLIKE SHORTCUTS
    #######################

    def mark(self, x, y):
        if x == self._last_x and y == self._last_y:
            return
        if x > 0xFFFF or x < 0 or y > 0xFFFF or y < 0:
            # Moves to out of range are not performed.
            return
        self.list_mark(x, y)

    def goto(self, x, y, long=None, short=None, distance_limit=None):
        if x == self._last_x and y == self._last_y:
            return
        if x > 0xFFFF or x < 0 or y > 0xFFFF or y < 0:
            # Moves to out of range are not performed.
            return
        if long is None:
            long = self.delay_jump_long
        if short is None:
            short = self.delay_jump_short
        if self._goto_speed is not None:
            self.set_travel_speed(self._goto_speed)
        distance = int(abs(complex(x, y) - complex(self._last_x, self._last_y)))
        delay = long if distance_limit and distance > distance_limit else short
        if delay:
            self.set_delay_jump(delay)
        self.list_jump(x, y)

    def light(self, x, y, long=None, short=None, distance_limit=None):
        if x == self._last_x and y == self._last_y:
            return
        if x > 0xFFFF or x < 0 or y > 0xFFFF or y < 0:
            # Moves to out of range are not performed.
            return
        if long is None:
            long = self.delay_jump_long
        if short is None:
            short = self.delay_jump_short
        if self.light_on():
            self.list_write_port()
        if self._light_speed is not None:
            self.set_travel_speed(self._light_speed)
        distance = int(abs(complex(x, y) - complex(self._last_x, self._last_y)))
        delay = long if distance_limit and distance > distance_limit else short
        if delay:
            self.set_delay_jump(delay)
        self.list_jump(x, y)

    def dark(self, x, y, long=None, short=None, distance_limit=None):
        if x == self._last_x and y == self._last_y:
            return
        if x > 0xFFFF or x < 0 or y > 0xFFFF or y < 0:
            # Moves to out of range are not performed.
            return
        if long is None:
            long = self.delay_jump_long
        if short is None:
            short = self.delay_jump_short
        if self.light_off():
            self.list_write_port()
        if self._dark_speed is not None:
            self.set_travel_speed(self._dark_speed)
        distance = int(abs(complex(x, y) - complex(self._last_x, self._last_y)))
        delay = long if distance_limit and distance > distance_limit else short
        if delay:
            self.set_delay_jump(delay)
        self.list_jump(x, y)

    def dwell(self, time_in_ms, delay_end=True):
        dwell_time = time_in_ms * 100  # Dwell time in ms units in 10 us
        while dwell_time > 0:
            d = min(dwell_time, 60000)
            self.list_laser_on_point(int(d))
            dwell_time -= d
        if delay_end:
            self.list_delay_time(int(self.delay_end / 10.0))

    def wait(self, time_in_ms):
        dwell_time = time_in_ms * 100  # Dwell time in ms units in 10 us
        while dwell_time > 0:
            d = min(dwell_time, 60000)
            self.list_delay_time(int(d))
            dwell_time -= d

    def wait_for_input(self, mask, value):
        self.initial_configuration()
        self._wait_for_input_protocol(mask, value)
        self.marking_configuration()

    def _wait_for_input_protocol(self, input_mask, input_value):
        required_passes = self.input_passes_required
        passes = 0
        while (
            self.connection and not self.connection.is_shutdown and not self._aborting
        ):
            read_port = self.connection.read_port()
            b = read_port[1]
            all_matched = True
            for i in range(16):
                if (input_mask >> i) & 1 == 0:
                    continue  # We don't care about this mask.
                if (input_value >> i) & 1 != (b >> i) & 1:
                    all_matched = False
                    time.sleep(0.05)
                    break

            if all_matched:
                passes += 1
                if passes > required_passes:
                    # Success, we matched the wait for protocol.
                    return
            else:
                passes = 0

    def set_xy(self, x, y):
        distance = int(abs(complex(x, y) - complex(self._last_x, self._last_y)))
        if distance > 0xFFFF:
            distance = 0xFFFF
        self.goto_xy(x, y, distance=distance)

    def get_last_xy(self):
        return self._last_x, self._last_y

    #######################
    # WAIT STATE COMMANDS
    #######################

    def is_busy(self):
        status = self.status()
        return bool(status & BUSY)

    def is_ready(self):
        status = self.status()
        return bool(status & READY)

    def is_ready_and_not_busy(self):
        status = self.status()
        return bool(status & READY) and not bool(status & BUSY)

    def wait_finished(self):
        while not self.is_ready_and_not_busy():
            time.sleep(0.01)
            if not self._sending:
                return

    def wait_ready(self):
        while not self.is_ready():
            time.sleep(0.01)
            if not self._sending:
                return

    def wait_idle(self):
        while self.is_busy():
            time.sleep(0.01)
            if not self._sending:
                return

    def abort(self, dummy_packet=True):
        with self._list_build_lock:
            self.stop_execute()
            self.set_fiber_mo(0)
            self.reset_list()
            if dummy_packet:
                self._list_new()
                self.list_end_of_list()  # Ensure packet is sent on end.
                self._list_end()
                if not self._list_executing:
                    self.execute_list()
            self._list_executing = False
            self._number_of_list_packets = 0
            self.set_fiber_mo(0)
            self.port_off(self.laser_pin)
            self.write_port()
            self.laser_configuration = "initial"

    def pause(self):
        self.paused = True
        self.stop_list()

    def resume(self):
        self.restart_list()
        self.paused = False

    def init_laser(self):
        self.usb_log("Initializing Laser")
        serial_number = self.get_serial_number()
        self.usb_log(f"Serial Number: {serial_number}")
        version = self.get_version()
        self.usb_log(f"Version: {version}")

        self.reset()
        self.usb_log("Reset")
        self.write_correction_file(self.cor_file)
        self.usb_log("Correction File Sent")
        self.enable_laser()
        self.usb_log("Laser Enabled")
        self.set_control_mode(self.control_mode)
        self.usb_log("Control Mode")
        self.set_laser_mode(self.laser_mode)
        self.usb_log("Laser Mode")
        self.set_delay_mode(self.delay_mode)
        self.usb_log("Delay Mode")
        self.set_timing(self.timing_mode)
        self.usb_log("Timing Mode")
        self.set_standby(self.standby_param_1, self.standby_param_2)
        self.usb_log("Setting Standby")
        self.set_first_pulse_killer(self.first_pulse_killer)
        self.usb_log("Set First Pulse Killer")
        self.set_pwm_half_period(self.pwm_half_period)
        self.usb_log("Set PWM Half-Period")
        self.set_pwm_pulse_width(self.pwm_pulse_width)
        self.usb_log("Set PWM pulse width")
        self.set_fiber_mo(0)  # Close
        self.usb_log("Set Fiber Mo (Closed)")
        self.set_pfk_param_2(
            self.fpk_max_voltage, self.fpk_min_voltage, self.fpk_t1, self.fpk_t2
        )
        self.usb_log("First Pulse Killer Parameters")
        self.set_fly_res(
            self.fly_resolution_1,
            self.fly_resolution_2,
            self.fly_resolution_3,
            self.fly_resolution_4,
        )
        self.usb_log("On-The-Fly Res")
        self.enable_z()
        self.usb_log("Z-Enabled")
        self.write_analog_port_1(0x7FF)
        self.usb_log("Analog Port 1")
        self.enable_z()
        self.usb_log("Z-Enabled-part2")
        time.sleep(0.05)
        self.usb_log("Ready")

    #######################
    # GPIO TOGGLE
    #######################

    def light_on(self):
        if not self.is_port(self.light_pin):
            self.port_on(self.light_pin)
            return True
        return False

    def light_off(self):
        if self.is_port(self.light_pin):
            self.port_off(self.light_pin)
            return True
        return False

    def is_port(self, bit):
        return bool((1 << bit) & self._port_bits)

    def port_on(self, bit):
        self._port_bits = self._port_bits | (1 << bit)

    def port_off(self, bit):
        self._port_bits = ~((~self._port_bits) | (1 << bit))

    def port_set(self, mask, values):
        self._port_bits &= ~mask  # Unset mask.
        self._port_bits |= values & mask  # Set masked bits.

    #######################
    # COR FILE MANAGEMENT
    #######################

    def write_correction_file(self, filename):
        if filename is None:
            self.write_blank_correct_file()
            return
        try:
            table = self._read_correction_file(filename)
            self._write_correction_table(table)
        except OSError:
            self.write_blank_correct_file()
            return

    @staticmethod
    def get_scale_from_correction_file(filename):
        with open(filename, "rb") as f:
            label = f.read(0x16)
            if label.decode("utf-16") == "LMC1COR_1.0":
                unk = f.read(2)
                return struct.unpack("63d", f.read(0x1F8))[43]
            else:
                unk = f.read(6)
                return struct.unpack("d", f.read(8))[0]

    def write_blank_correct_file(self):
        self.write_cor_table(False)

    def _read_float_correction_file(self, f):
        """
        Read table for cor files marked: LMC1COR_1.0
        @param f:
        @return:
        """
        table = []
        for j in range(65):
            for k in range(65):
                dx = int(round(struct.unpack("d", f.read(8))[0]))
                dx = dx if dx >= 0 else -dx + 0x8000
                dy = int(round(struct.unpack("d", f.read(8))[0]))
                dy = dy if dy >= 0 else -dy + 0x8000
                table.append([dx & 0xFFFF, dy & 0xFFFF])
        return table

    def _read_int_correction_file(self, f):
        table = []
        for j in range(65):
            for k in range(65):
                dx = int.from_bytes(f.read(4), "little", signed=True)
                dx = dx if dx >= 0 else -dx + 0x8000
                dy = int.from_bytes(f.read(4), "little", signed=True)
                dy = dy if dy >= 0 else -dy + 0x8000
                table.append([dx & 0xFFFF, dy & 0xFFFF])
        return table

    def _read_correction_file(self, filename):
        """
        Reads a standard .cor file and builds a table from that.

        @param filename:
        @return:
        """
        with open(filename, "rb") as f:
            label = f.read(0x16)
            if label.decode("utf-16") == "LMC1COR_1.0":
                header = f.read(0x1FA)
                return self._read_float_correction_file(f)
            else:
                header = f.read(0xE)
                return self._read_int_correction_file(f)

    def _write_correction_table(self, table):
        assert len(table) == 65 * 65
        self.write_cor_table(True)
        first = True
        for dx, dy in table:
            self.write_cor_line(dx, dy, 0 if first else 1)
            first = False

    #######################
    # LASER PARAMETER SET
    #######################

    def set(
        self,
        mark_speed=None,
        travel_speed=None,
        power=None,
        frequency=None,
        pulse_width=None,
        delay_on=None,
        delay_off=None,
        delay_polygon=None,
    ):
        if mark_speed is None:
            mark_speed = self.mark_speed
        if travel_speed is None:
            travel_speed = self.travel_speed
        if power is None:
            power = self.power
        if frequency is None:
            frequency = self.frequency
        if pulse_width is None:
            pulse_width = self.pulse_width
        if delay_on is None:
            delay_on = self.delay_laser_on
        if delay_off is None:
            delay_off = self.delay_laser_off
        if delay_polygon is None:
            delay_polygon = self.delay_polygon
        self.set_pulse_width(pulse_width)

        self.set_travel_speed(travel_speed)
        self.set_power(power)
        self.set_frequency(frequency)
        self.set_mark_speed(mark_speed)
        self.set_delay_on(delay_on)
        self.set_delay_off(delay_off)
        self.set_delay_polygon(delay_polygon)

    def set_travel_speed(self, speed):
        if self._travel_speed == speed:
            return
        if speed and self._travel_speed != speed:
            self.list_jump_speed(self._convert_speed(speed))
            self._travel_speed = speed

    def set_mark_speed(self, speed):
        if self._speed == speed:
            return
        self._speed = speed
        c_speed = self._convert_speed(speed)
        self.list_mark_speed(c_speed)

    def set_delay_on(self, delay):
        if self._delay_on == delay:
            return
        self._delay_on = delay
        self.list_laser_on_delay(delay)

    def set_delay_off(self, delay):
        if self._delay_off == delay:
            return
        self._delay_off = delay
        self.list_laser_off_delay(delay)

    def set_delay_polygon(self, delay):
        if self._delay_poly == delay:
            return
        self._delay_poly = delay
        self.list_polygon_delay(delay)

    def set_delay_jump(self, delay):
        if self._delay_jump == delay:
            return
        self._delay_jump = delay
        self.list_jump_delay(delay)

    def set_power(self, power):
        """
        Accepts power in percent, automatically converts to power_ratio

        @param power:
        @return:
        """
        if self._power == power or power is None:
            return
        self._power = power
        self.list_mark_current(self._convert_power(power))

    def set_frequency(self, frequency):
        if self._frequency == frequency or frequency is None:
            return
        self._frequency = frequency
        self.list_qswitch_period(self._convert_frequency(frequency))

    def set_pulse_width(self, pulse_width):
        if self._pulse_width == pulse_width or pulse_width is None:
            return
        self._pulse_width = self.pulse_width
        self.list_fiber_ylpm_pulse_width(self.pulse_width)

    #######################
    # UNIT CONVERSIONS
    #######################

    def _convert_speed(self, speed):
        """
        Speed in the galvo is given in galvos/ms this means mm/s needs to multiply by galvos_per_mm
        and divide by 1000 (s/ms)

        @param speed:
        @return:
        """
        # return int(speed / 2)
        galvos_per_mm = abs(self.galvos_per_mm)
        return int(speed * galvos_per_mm / 1000.0)

    def _convert_frequency(self, frequency_khz):
        """
        Converts frequency to period.

        20000000.0 / frequency in hz

        @param frequency_khz: Frequency to convert
        @return:
        """
        return int(round(20000.0 / frequency_khz)) & 0xFFFF

    def _convert_power(self, power):
        """
        Converts power percent to int value
        @return:
        """
        return int(round(power * 0xFFF / 100.0))

    #######################
    # LIST MANGEMENT
    #######################

    def _list_end(self):
        with self._list_build_lock:
            if self._active_list and self._active_index:
                self.wait_ready()
                while self.paused:
                    time.sleep(0.3)
                self.send(self._active_list, False)
                self.set_end_of_list(0)
                self._number_of_list_packets += 1
                self._active_list = None
                self._active_index = 0
                if self._number_of_list_packets > 2 and not self._list_executing:
                    self.execute_list()
                    self._list_executing = True

    def _list_new(self):
        with self._list_build_lock:
            self._active_list = copy(empty)
            self._active_index = 0

    def _list_write(self, command, v1=0, v2=0, v3=0, v4=0, v5=0):
        if self._active_index >= 0xC00:
            self._list_end()
        with self._list_build_lock:
            if self._active_list is None:
                self._list_new()
            index = self._active_index
            self._active_list[index : index + 12] = struct.pack(
                "<6H", int(command), int(v1), int(v2), int(v3), int(v4), int(v5)
            )
            self._active_index += 12

    def _command(self, command, v1=0, v2=0, v3=0, v4=0, v5=0, read=True):
        cmd = struct.pack(
            "<6H", int(command), int(v1), int(v2), int(v3), int(v4), int(v5)
        )
        return self.send(cmd, read=read)

    #######################
    # RAW LIST COMMANDS
    #######################

    def list_jump(self, x, y, angle=0):
        distance = int(abs(complex(x, y) - complex(self._last_x, self._last_y)))
        if distance > 0xFFFF:
            distance = 0xFFFF
        x = int(x)
        y = int(y)
        self._list_write(listJumpTo, x, y, angle, distance)
        self._last_x = x
        self._last_y = y

    def list_end_of_list(self):
        self._list_write(listEndOfList)

    def list_laser_on_point(self, dwell_time):
        self._list_write(listLaserOnPoint, dwell_time)

    def list_delay_time(self, time):
        """
        Delay time in 10 microseconds units

        @param time:
        @return:
        """
        self._list_write(listDelayTime, abs(time))

    def list_mark(self, x, y, angle=0):
        distance = int(abs(complex(x, y) - complex(self._last_x, self._last_y)))
        if distance > 0xFFFF:
            distance = 0xFFFF
        x = int(x)
        y = int(y)
        self._list_write(listMarkTo, x, y, angle, distance)
        self._last_x = x
        self._last_y = y

    def list_jump_speed(self, speed):
        if speed > 0xFFFF:
            speed = 0xFFFF
        self._list_write(listJumpSpeed, speed)

    def list_laser_on_delay(self, delay):
        """
        Set laser on delay in microseconds
        @param delay:
        @return:
        """
        self._list_write(listLaserOnDelay, abs(delay), 0x0000 if delay > 0 else 0x8000)

    def list_laser_off_delay(self, delay):
        """
        Set laser off delay in microseconds
        @param delay:
        @return:
        """
        self._list_write(listLaserOffDelay, abs(delay), 0x0000 if delay > 0 else 0x8000)

    def list_mark_frequency(self, frequency):
        """
        This command is used in some machines but, it's not clear given the amount of reverse engineering how those
        values are set. This is done for laser_type = 4.

        @param frequency:
        @return:
        """
        # listMarkFreq
        raise NotImplementedError

    def list_mark_power_ratio(self, power_ratio):
        """
        This command is used in some machines. Laser_type=4 and laser_type=0 (CO2), if 0x800A returned 0.

        @param power_ratio:
        @return:
        """
        # listMarkPowerRatio
        self._list_write(listMarkPowerRatio, power_ratio)

    def list_mark_speed(self, speed):
        """
        Sets the marking speed for the laser.

        @param speed:
        @return:
        """
        if speed > 0xFFFF:
            speed = 0xFFFF
        self._list_write(listMarkSpeed, speed)

    def list_jump_delay(self, delay):
        """
        Set laser jump delay in microseconds
        @param delay:
        @return:
        """
        self._list_write(listJumpDelay, abs(delay), 0x0000 if delay > 0 else 0x8000)

    def list_polygon_delay(self, delay):
        """
        Set polygon delay in microseconds
        @param delay:
        @return:
        """
        self._list_write(listPolygonDelay, abs(delay), 0x0000 if delay > 0 else 0x8000)

    def list_write_port(self):
        """
        Writes the set port values to the list.

        @return:
        """
        self._list_write(listWritePort, self._port_bits)

    def list_mark_current(self, current):
        """
        Also called as part of setting the power ratio. This is not correctly understood.
        @param current:
        @return:
        """
        # listMarkCurrent
        self._list_write(listMarkCurrent, current)

    def list_mark_frequency_2(self, frequency):
        """
        Also called as part of setting frequency and is not correctly understood.

        @param frequency:
        @return:
        """
        # listMarkFreq2
        raise NotImplementedError

    def list_fly_enable(self, enabled=1):
        """
        On-The-Fly control enable/disable within list.

        @param enabled:
        @return:
        """
        self._list_write(listFlyEnable, enabled)

    def list_qswitch_period(self, qswitch):
        """
        Sets the qswitch period, which in is the inversely related to frequency.

        @param qswitch:
        @return:
        """
        self._list_write(listQSwitchPeriod, qswitch)

    def list_direct_laser_switch(self):
        """
        This is not understood.
        @return:
        """
        # ListDirectLaserSwitch
        raise NotImplementedError

    def list_fly_delay(self, delay):
        """
        On-the-fly control.

        @param delay:
        @return:
        """
        self._list_write(listFlyDelay, abs(delay), 0x0000 if delay > 0 else 0x8000)

    def list_set_co2_fpk(self):
        """
        Set the CO2 Laser, First Pulse Killer.

        @return:
        """
        self._list_write(listSetCo2FPK)

    def list_fly_wait_input(self):
        """
        Sets the On-the-fly to wait for input.
        @return:
        """
        self._list_write(listFlyWaitInput)

    def list_fiber_open_mo(self, open_mo):
        """
        Sets motion operations, without MO set the laser does not automatically fire while moving.

        @param open_mo:
        @return:
        """
        self._list_write(listFiberOpenMO, open_mo)

    def list_wait_for_input(self, wait_mask, wait_level):
        """
        Unknown.

        @return:
        """
        self._list_write(listWaitForInput, wait_mask, wait_level)

    def list_change_mark_count(self, count):
        """
        Unknown.

        @param count:
        @return:
        """
        self._list_write(listChangeMarkCount, count)

    def list_set_weld_power_wave(self, weld_power_wave):
        """
        Unknown.

        @param weld_power_wave:
        @return:
        """
        self._list_write(listSetWeldPowerWave, weld_power_wave)

    def list_enable_weld_power_wave(self, enabled):
        """
        Unknown.

        @param enabled:
        @return:
        """
        self._list_write(listEnableWeldPowerWave, enabled)

    def list_fiber_ylpm_pulse_width(self, pulse_width):
        """
        Unknown.

        @param pulse_width:
        @return:
        """
        self._list_write(listFiberYLPMPulseWidth, pulse_width)

    def list_fly_encoder_count(self, count):
        """
        Unknown.

        @param count:
        @return:
        """
        self._list_write(listFlyEncoderCount, count)

    def list_set_da_z_word(self, word):
        """
        Unknown.

        @param word:
        @return:
        """
        self._list_write(listSetDaZWord, word)

    def list_jpt_set_param(self, param):
        """
        Unknown.

        @param param:
        @return:
        """
        self._list_write(listJptSetParam, param)

    def list_ready(self):
        """
        Seen at the start of any new command list.

        @return:
        """
        self._list_write(listReadyMark)

    #######################
    # RAW REALTIME COMMANDS
    #######################

    def disable_laser(self):
        return self._command(DisableLaser)

    def enable_laser(self):
        return self._command(EnableLaser)

    def execute_list(self):
        return self._command(ExecuteList)

    def set_pwm_pulse_width(self, pulse_width):
        return self._command(SetPwmPulseWidth, pulse_width)

    def get_version(self):
        return self._command(GetVersion)

    def get_serial_number(self):
        return self._command(GetSerialNo)

    def get_list_status(self):
        return self._command(GetListStatus)

    def get_position_xy(self):
        return self._command(GetPositionXY)

    def goto_xy(self, x, y, angle=0, distance=0):
        self._last_x = x
        self._last_y = y
        return self._command(GotoXY, int(x), int(y), int(angle), int(distance))

    def laser_signal_off(self):
        return self._command(LaserSignalOff)

    def laser_signal_on(self):
        return self._command(LaserSignalOn)

    def write_cor_line(self, dx, dy, non_first):
        self._command(WriteCorLine, dx, dy, non_first, read=False)

    def reset_list(self):
        return self._command(ResetList)

    def restart_list(self):
        return self._command(RestartList)

    def write_cor_table(self, table: bool = True):
        return self._command(WriteCorTable, int(table))

    def set_control_mode(self, mode):
        return self._command(SetControlMode, mode)

    def set_delay_mode(self, mode):
        return self._command(SetDelayMode, mode)

    def set_max_poly_delay(self, delay):
        return self._command(
            SetMaxPolyDelay, abs(delay), 0x0000 if delay > 0 else 0x8000
        )

    def set_end_of_list(self, end):
        return self._command(SetEndOfList, end)

    def set_first_pulse_killer(self, fpk):
        return self._command(SetFirstPulseKiller, fpk)

    def set_laser_mode(self, mode):
        return self._command(SetLaserMode, mode)

    def set_timing(self, timing):
        return self._command(SetTiming, timing)

    def set_standby(self, standby1, standby2):
        return self._command(SetStandby, standby1, standby2)

    def set_pwm_half_period(self, pwm_half_period):
        return self._command(SetPwmHalfPeriod, pwm_half_period)

    def stop_execute(self):
        return self._command(StopExecute)

    def stop_list(self):
        return self._command(StopList)

    def write_port(self):
        return self._command(WritePort, self._port_bits)

    def write_analog_port_1(self, port):
        return self._command(WriteAnalogPort1, port)

    def write_analog_port_2(self, port):
        return self._command(WriteAnalogPort2, port)

    def write_analog_port_x(self, port):
        return self._command(WriteAnalogPortX, port)

    def read_port(self):
        return self._command(ReadPort)

    def set_axis_motion_param(self, param):
        return self._command(SetAxisMotionParam, param)

    def set_axis_origin_param(self, param):
        return self._command(SetAxisOriginParam, param)

    def axis_go_origin(self):
        return self._command(AxisGoOrigin)

    def move_axis_to(self, a):
        return self._command(MoveAxisTo)

    def get_axis_pos(self):
        return self._command(GetAxisPos)

    def get_fly_wait_count(self):
        return self._command(GetFlyWaitCount)

    def get_mark_count(self):
        return self._command(GetMarkCount)

    def set_pfk_param_2(self, param1, param2, param3, param4):
        return self._command(SetFpkParam2, param1, param2, param3, param4)

    def set_fiber_mo(self, mo):
        """
        mo == 0 close
        mo == 1 open

        @param mo:
        @return:
        """
        return self._command(Fiber_SetMo, mo)

    def get_fiber_st_mo_ap(self):
        return self._command(Fiber_GetStMO_AP)

    def enable_z(self):
        return self._command(EnableZ)

    def disable_z(self):
        return self._command(DisableZ)

    def set_z_data(self, zdata):
        return self._command(SetZData, zdata)

    def set_spi_simmer_current(self, current):
        return self._command(SetSPISimmerCurrent, current)

    def set_fpk_param(self, param):
        return self._command(SetFpkParam, param)

    def reset(self):
        return self._command(Reset)

    def get_fly_speed(self):
        return self._command(GetFlySpeed)

    def fiber_pulse_width(self):
        return self._command(FiberPulseWidth)

    def get_fiber_config_extend(self):
        return self._command(FiberGetConfigExtend)

    def input_port(self, port):
        return self._command(InputPort, port)

    def clear_lock_input_port(self):
        return self._command(InputPort, 0x04)

    def enable_lock_input_port(self):
        return self._command(InputPort, 0x02)

    def disable_lock_input_port(self):
        return self._command(InputPort, 0x01)

    def get_input_port(self):
        return self._command(InputPort)

    def get_mark_time(self):
        """
        Get Mark Time is always called with data 3. With 0 it returns 0. It is unknown what the payload means.
        @return:
        """
        return self._command(GetMarkTime, 3)

    def get_user_data(self):
        return self._command(GetUserData)

    def set_fly_res(self, fly_res1, fly_res2, fly_res3, fly_res4):
        return self._command(SetFlyRes, fly_res1, fly_res2, fly_res3, fly_res4)
