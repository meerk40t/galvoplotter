# galvoplotter
low level command system for ezcad2 lmc-controller galvo lasers

# Dependencies
* pyusb

# API

## Plot
The lower level api should interact with the ezcad2 lmc-controller, and provide plotlike commands for the major laser operations.

These commands are:
* `.mark(x,y)` firing the laser with the given parameters to the given location.
* `.goto(x,y)` move to a location regardless of the state of the redlight.
* `.light(x,y)` move to a location using the outline redlight.
* `.dark(x,y)` move to a location without the redlight being turned on.

In many galvo setups you can toggle the light on and off and create shapes and outlines with the laser. This is especially true if you have specific control over the lighting state. The speed of each should be able to be set independently as there are good reasons to move more quickly with the redlight-off than when it's on.

## Realtime
Outside of the primary drawing routine many commands can be issued to the controller to control how it is processing things, and to query the process for information. Most of the regular plotting commands are sent as a command-list the execution of these lists can be paused, resumed, or aborted. However, this generally must be done from a different thread than the one writing the plotted list data. Since this is mostly controlling the machine state and we cannot write the data and modify the routines as well.