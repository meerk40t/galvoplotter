# galvoplotter
low level command system for ezcad2 lmc-controller galvo lasers

# Installing
galvo plotter can be installed with `pip`
`pip install galvoplotter`

# Dependencies
* pyusb

# Goals
The primary goal of this project is to make for easy interactions with the lmc-controller board. Interactions that can be low-level enough to exactly allow the user to send exactly the data they want, or high level enough to allow the user to quickly implement their code and send it to the laser without needing to know anything about how that was done. 

# Support
Currently, BJJCZ `fiber` and `co2` lasers are supported. By default, `fiber` would be assumed but you can specify `source` to be `co2` or `fiber` so that some commands like `controller.set(power=25, frequency=20)` will work with the device specific aspects.  

# Realtime/Sequential
Like most laser cutters, there are two classes of commands: realtime and sequential. The realtime commands usually perform actions like `status`, `jogging`, `pause`, `resume`, `abort`. This differs from controller to controller but this same general distinction holds true. There are two different classes of commands: ones that should be executed sequentially in order and the ones that should be executed immediately.

There are two primary threads, `main` and `spooler`. The spooler thread will execute a series of jobs in sequential order. Realtime control over this execution cannot occur within that thread, since many of these commands take time to execute and the thread for executing the job cannot correctly modulate the execution of that job, while writing the job. Some jobs may also be infinite meaning that the code used to create them will not natively terminate, this also prevents us from pre-caching of the job (you can't cache an infinite job).

### Example 1

However, for many applications it is sufficient to use the controller and connection. For example:


```python
    controller = GalvoController(settings_file="<my_settings>.json")
    with controller.marking() as c:
        c.goto(0x5000, 0x5000)
        c.mark(0x5000, 0xA000)
        c.mark(0xA000, 0xA000)
        c.mark(0x5000, 0xA000)
        c.mark(0x5000, 0x5000)
    controller.wait_for_machine_idle()
```

Will quickly mark a square on the bed with default settings, without needing to use the spooler or writing a job.

### Example 2

However, sometimes you may need to cancel a job while it's running, or write an infinite job. For example:

```python
        controller = GalvoController(settings_file="<my_settings>.json")

        def my_job(c):
            c.lighting_configuration()
            c.dark(0x8000, 0x8000)
            c.light(0x2000, 0x2000)
            return False

        controller.submit(my_job)
        time.sleep(2)
        controller.shutdown()
```

This creates a job `my_job(c)` and submits it to the spooler. This would not complete (the job does not end). It would simply draw the same light-line between `0x8000,0x8000` and `0x2000, 0x2000` forever. However, after sleeping the current thread (`main`) for `2` seconds we call `shutdown()` which aborts the job in progress.

# Components
There are 4 primary components used with galvoplotter: controller, connection, spooler, and job.

## Controller
The controller serves as the bridge between your software and the lmc-controller board. It facilitates communication by translating internally used command codes into function calls. The controller houses all the realtime and sequential commands available for interaction. Sequential commands can be easily added to an active list until they are closed and sent to the laser. 

The controller has three general states. `init` when the controller exists and things can be done with it. `shutting down` and `shutdown` when `shutdown()` is called all components should go ahead and stop what they are doing as quick as they can. This includes aborting any operations occurring in the laser (with an `abort()` command). If the laser should finish, rather than shutdown one of the `wait_xx` commands should be called. 

## Connection
The connection component provides a low-level interface for raw command communication. The primary commands are `open()`, `close()`, `write()` and `read()`.

In most cases, the connection will connect automatically when we need to send data.

There are two primary connections, `usb_connection` which connects to the laser via usb (requires `pyusb`) and `mock_connection` which just pretends to connect to something but prints all the relevant debug data.

The connection has 5 primary states.

* `init`: Connection is not opened. We have never connected.
* `opening`: Connection is establishing.
* `opened`: Connection is open. Laser has responded and appears correct.
* `closed`: Connection was opened, but has since been closed.
* `aborted`: Connection could not be established after reasonable attempts. Disconnect is required to clear the aborted state.

## Spooler
Unlike other parts of the system, the spooler is optional, and the spooler does not start automatically. It starts only when jobs are submitted. It continues until the queue has completed. Pausing will block the spooler from starting the next job, or re-entering the current job.

The spooler serves to help facilitate sequential interactions, and free up the current thread for manipulating the laser. While lists are the primary method of sending a series of sequential commands to the lmc-controller, this does not cover all the potential workflows. Sometimes a series of small jobs is required, or an infinite lighting job followed by an infinite marking job (each requiring an explicit cancel to be issued from the realtime thread), and a lot of other potential workflows not otherwise explicitly stated.
 

## Job
Jobs consist of a function to be called. This function should return `True` if the function was fully-processed. Otherwise, it will be executed repeatedly by the spooler until it returns `True` (which never happen). Between executions the spooler can be paused, aborted, or the job may be removed.


# Laser Configurations
There are three laser configurations.
* `initial`: We are only sending realtime commands and no sequential command lists are being sent.
* `marking`: We should be sending marking packets the laser should be ready to fire, we can also send lighting jobs. But, we require that all the attributes needed for marking should be fully initialized.
* `lighting`: We should only be sending lighting packets and the laser should not need to fire, and may not be ready to fire.

Note: To send the buffer written in the `marking` or `lighting` configuration you must return to `initial` configuration.


### contexts: marking()/lighting()
There are context managers for the `controller.marking()` and `controller.lighting()` commands. These are shortcuts for setting the `controller.marking_configuration()` and then restoring this to `controller.initial_configuration()` when finished. And likewise for the `lighting()` command.

```python
    controller = GalvoController(settings_file="<my_settings>.json")
    with controller.marking() as c:
        c.goto(0x8000, 0x8000)
        c.dwell(100)
    controller.wait_for_machine_idle()
```
This would, for example, fire the laser for 100ms in the center of the area. During the use of the `marking()` context, our commands are executed in the `controller.marking_configuration()` it's restored to the `initial_configuration` on exit which will execute any list commands in the buffer.


# Midlevel Commands
The controller should have direct access to the all low level commands. This permits access to all the functions of the laser, however directly operating at this level is often difficult and unneeded.

## Plotlike commands

The plotlike commands are used to send positional data to the laser. 
* `.mark(x,y)` firing the laser with the given parameters to the given location.
* `.goto(x,y)` move to a location regardless of the state of the redlight.
* `.light(x,y)` move to a location using the outline redlight.
* `.dark(x,y)` move to a location without the redlight being turned on.
* `.dwell(time_in_ms)` fires the laser at the current position for the time specified.
* `.wait(time_in_ms)` waits without the laser firing at the current position for the time specified.

These commands also have their own speed settings. `mark_speed` is inherent to the laser, the remaining three `goto_speed`, `light_speed` and `dark_speed` have the `travel_speed` switched before the lower level `list_jump()` is called. Often you may want a different speed for movements with the laser off than you would for movements with the laser on.  

## Helpers
Midlevel realtime commands are executed realtime but require some additional code to be more helpful.

### Realtime
* `.jog(x,y)` this does a realtime goto (called `goto_xy`) with correct distance calculations (needed to avoid a popping sound in the head).

### Hybrid
This commands operated differently in different configurations. In `initial_configuration` this sends a realtime GPIO change, however in either `lighting` or `marking` it will send a list-sequential GPIO change.

* `.light_on()` this turns the redlight on.
* `.light_off()` this turns the redlight off.

# Wait Commands
In many cases we want the current thread to block until some event has occurred.

* `wait_for_spooler_job_sent(job)` blocks until the specified job is sent.
* `wait_for_machine_idle()` blocks until machine is idle, spooler must have fully sent, and laser must give a finished status.
* `wait_for_spooler_send()` blocks until all jobs in the spooler are sent (they may still be buffered in the laser)
* `wait_finished()` blocks until the controller is finished.
* `wait_ready()` waits until the device status is flagged `ready` and can accept additional packets
* `wait_idle()` waits until the device status is not flagged as `busy` and is no longer doing work.

Note: if you sent an infinite job. And you call `wait_for_spooler_job_sent()` or `wait_for_machine_idle()` you may end up livelocking the main thread, as those states are unreachable. It may, however, terminate if the connection were broken.

# Examples
See https://github.com/meerk40t/galvoplotter/tree/main/examples for example scripts.

# Thanks
* Bryce Schroeder - Did the initial work for reverse engineering the format for the laser.
  * See: https://gitlab.com/bryce15/balor for his project.
* inpain / tiger12506 - Did considerable debugging with galvo lasers to facilitate the reverse engineering.
* Sandor Konya - Introductions, advice and support