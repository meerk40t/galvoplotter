# galvoplotter
low level command system for ezcad2 lmc-controller galvo lasers

# Dependencies
* pyusb

# Goals
The primary goal of this project is to make for easy interactions with the lmc-controller board. Interactions that can be low-level enough to exactly allow the user to send exactly the data they want, or high level enough to allow the user to quickly implement their code and send it to the laser without needing to know anything about how that was done. 

# Realtime/Sequential
Like most laser cutters, there are two classes of commands: realtime and sequential. The realtime commands usually perform actions like `status`, `jogging`, `pause`, `resume`, `abort`. This differs from controller to controller but this same general distinction holds true. There are two different classes of commands: ones that should be executed sequentially in order and the ones that should be executed immediately.

There are two primary threads, `main` and `spooler`. The spooler thread will execute a series of jobs in sequential order. Realtime control over this execution cannot occur within that thread, since many of these commands take time to execute and the thread for executing the job cannot correctly modulate the execution of that job, while writing the job. Some jobs may also be infinite meaning that the code used to create them will not natively terminate.


# Components
There are 4 primary components used with galvoplotter: controller, connection, spooler, and job.

## Controller
The controller deals primarily with interactions between the lmc-controller board and the software. The controller contains all the realtime and sequential commands that can be issued to the controller board. This is intended to facilitate the communications between the user of this library and the controller board, serving to translate the internally used command code into function calls. Sequential list-based commands are merely added to an active list until that list is closed and sent. When the number of commands exceeds 256 it will automatically send that part of the list.

### States
The controller has three general states. First is `init` the controller exists and things can be done with it. The second is `shutting down` and the last is `shutdown`. When `shutdown()` is called all components should go ahead and stop what they are doing as quick as they can. This includes aborting any operations occurring in the laser. If the laser should finish, rather than shutdown one of the `wait` commands should be called. 

## Connection
The connection is the lowest level interface. It serves as the primary method of communication for raw commands. The primary commands are `open()`, `close()`, `write()` and `read()`. How those interactions work is abstracted from the rest of the system.

There are two primary connections, `usb_connection` which connects to the laser via usb (requires `pyusb`) and `mock_connection` which just pretends to connect to something but prints all the relevant debug data.

### States
The connection has 5 primary states.

* `init`: Connection is not opened. We have never connected.
* `opening`: Connection is establishing.
* `opened`: Connection is open. Laser has responded and appears correct.
* `closed`: Connection was opened, but has since been closed.
* `aborted`: Connection could not be established after reasonable attempts. Disconnect is required to clear the aborted state.

## Spooler
The spooler serves to help facilitate sequential low-level interactions. While the primary method of sending a series of sequential commands for the lmc_controller are lists, this does not cover all the potential workflows. Sometimes a series of small jobs is required, or an infinite lighting job followed by an infinite marking job (each requiring an explicit cancel to be issued from the realtime thread).


### States
Unlike other parts of the system, the spooler is optional, and the spooler does not start automatically. It starts only when jobs are submitted. It continues until the queue has completed. Pausing will block the spooler from starting the next job, or re-entering the current job.  


## Job
Jobs primarily consist of a function to be called. This function should return `True` if the function was fully-processed. Otherwise, it will be executed repeatedly by the spooler until it such time as it returns `True` (which it may never do). Between executions the spooler can be paused, aborted, etc.


# Laser Configurations
There are three laser configurations.
* `initial`: We are only sending realtime commands and no sequential command lists are being sent.
* `marking`: We should be sending marking packets the laser should be ready to fire, we can also send lighting jobs. But, we require that all the attributes needed for marking should be fully initialized.
* `lighting`: We should only be sending lighting packets and the laser should not need to fire, and may not be ready to fire.


# Midlevel commands
The controller should have direct access to the all low level commands. This permits access to all the functions of the laser, however directly operating at this level is difficult.

### Plotlike commands

The plotlike commands are used to send positional data to the laser. 
* `.mark(x,y)` firing the laser with the given parameters to the given location.
* `.goto(x,y)` move to a location regardless of the state of the redlight.
* `.light(x,y)` move to a location using the outline redlight.
* `.dark(x,y)` move to a location without the redlight being turned on.
* `.dwell(time_in_ms)` fires the laser at the current position for the time specified.
* `.wait(time_in_ms)` waits without the laser firing at the current position for the time specified.

These commands also have their own speed settings. `mark_speed` is inherent to the laser, the remaining three `goto_speed`, `light_speed` and `dark_speed` have the `travel_speed` switched before the lower level `list_jump()` is called. Often you may want a different speed for movements with the laser off than you would for movements with the laser on.  

### Helpers
Midlevel realtime commands are executed realtime but require some additional code to be more helpful.

#### Realtime
* `.jog(x,y)` this does a realtime goto (called `goto_xy`) with correct distance calculations (needed to avoid a popping sound in the head).

#### Hybrid
This commands operated differently in different configurations. In `initial_configuration` this sends a realtime GPIO change, however in either `lighting` or `marking` it will send a list-sequential GPIO change.

* `.light_on()` this turns the redlight on.
* `.light_off()` this turns the redlight off.

### contexts: marking()/lighting()
There are context managers for the `controller.marking()` and `controller.lighting()` commands. These are shortcuts for setting the `controller.marking_configuration()` and then restoring this to `controller.initial_configuration()` when finished. And likewise for the `lighting()` command.

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
This would, for example, mark draw a square. During the use of the `marking()` context, our commands are executed in the `controller.marking_configuration()` it's restored to the `initial_configuration` on exit which will execute any list commands in the buffer.
