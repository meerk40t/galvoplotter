# galvoplotter
low level command system for ezcad2 lmc-controller galvo lasers

# Dependencies
* pyusb

# Goals
The primary goal of this project is to make for easy interactions with the lmc-controller board. Interactions that can be low-level enough to exactly allow the user to send exactly the data they want, or high level enough to allow the user to quickly implement their code and send it to the laser without needing to know anything about how that was done. 

# Realtime/Sequential
Like most laser cutters, there are two different classes of commands: realtime and sequential. The realtime commands usually perform actions like `status`, `jogging`, `pause`, `resume`, `abort`. This differs from controller to controller but this same general distinction holds true. There are two different classes of commands: ones that should be executed sequentially in order and the ones that should be executed immediately.

There are two primary threads, `main` and `spooler`. The spooler thread will execute a series of jobs in sequential order. Realtime control over this execution cannot occur within that thread, since many of these commands take time to execute and the thread for executing the job cannot correctly modulate the execution of that job, while writing the job. Some jobs may also be infinite meaning that the code used to create them will not natively terminate.

Therefore, even a low level command system should help facilitate the use and understanding of this distinction.


# Components
There are 4 primary object types used with galvoplotter: controller, connection, spooler, and job.

## Controller
The controller deals primarily with interactions between the lmc-controller board and the software. The controller contains all the realtime and sequential commands that can be issued to the controller board. This is intended to facilitate the communications between the user of this library and the controller board, serving to translate the internally used command code into function calls. Sequential list-based commands are merely added to an active list until that list is closed and sent. When the number of commands exceeds 256 it will automatically send that part of the list.

### Lifecycle
There are three controller states. The first is merely `init`; we have a controller. At some point with the controller we call `shutdown()` which leads to two states. `shutting_down` and `shutdown`. 
* `init`: The controller exists. We can do things with it.
* `shutting_down`: The controller is shutting down. Processes should abort and stop.
* `shutdown`: The controller was shutdown. All things were successfully ended.

## Connection
The connection is the lowest level interface. It serves as the primary method of communication for raw commands. The primary commands are `open()`, `close()`, `write()` and `read()`. How those interactions work is irrelevant to the rest of the system.

There are two primary connections, these are `usb_connection` which connects to the laser via usb (requires `pyusb`) and `mock_connection` which just pretends to connect to something but prints all the relevant debug data.

### Lifecycle
There are five connection states.
* `init`: Connection is not opened. We have never connected.
* `opening`: Connection is establishing.
* `opened`: Connection is open. Laser has responded and appears correct.
* `closed`: Connection was opened, but has since been closed.
* `aborted`: Connection could not be established after reasonable attempts. Disconnect is required to clear the aborted state.

## Spooler
The spooler serves to help facilitate sequential low level interactions. While the primary method of sending a series of sequential commands for the lmc_controller are lists, this does not cover all the potential workflows. Sometimes a series of small jobs is required, or an infinite lighting job followed by an infinite marking job (each requiring a cancel to be issued from the realtime thread).

`Pause()` is primarily to called to ensure no job is currently running and that the list of jobs can be manipulated as a block without the spooler trying to do things.

### Lifecycle
There are four spooler states.
* `init`: the spooler thread process was not started. 
* `started`: The spooler is started and jobs submitted shall be executed in sequential order.
* `paused`: The spooler is paused, upon `resume()` it returns to `executing` or `started` state.
* `executing`: The spooler is started and jobs are currently being executed.

## Job
Jobs primarily consist of a function to be called. This function returns `True` if the function was fully-processed. It will execute repeatedly by the spooler until it returns True to indicate completion. Between executions the spooler can be paused and abort, etc.

### Lifecycle
There are at least five job states.
* `init`: This job exists, but it is not slated to be executed.
* `queue`: This job is in the spooler queue.
* `running`: This job is the currently running job in the spooler.
* `finished`: This job finished naturally by returning `True` for its execution response.
* `cancelled`: This job was cancelled while it was being executed, or before it was to be executed.


# Plot
There are three plotting states.
* `rapid`: We are only sending realtime commands and no sequential command lists are being sent.
* `program`: We should be sending marking packets the laser should be ready to fire.
* `light`: We should only be sending lighting packets and the laser should not need to fire.

Do note that program mode can also send regular light commands, but in lighting mode some required states are not used
and marking with the laser might not be possible.

## Plotlike-commands
The lower level api should interact with the ezcad2 lmc-controller, and provide plotlike commands for the major laser operations.

These commands are:
* `.mark(x,y)` firing the laser with the given parameters to the given location.
* `.goto(x,y)` move to a location regardless of the state of the redlight.
* `.light(x,y)` move to a location using the outline redlight.
* `.dark(x,y)` move to a location without the redlight being turned on.

In many galvo setups you can toggle the light on and off and create shapes and outlines with the laser. This is especially true if you have specific control over the lighting state. The speed of each should be able to be set independently as there are good reasons to move more quickly with the redlight-off than when it's on.
