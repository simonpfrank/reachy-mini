"""Our on-device tools for the Reachy Mini conversation app.

Each module is one tool file, copied to the robot's external tools folder and loaded by the app by name.
Standard library only: the tools run inside the app's own environment, where extra packages could break it.
Shared code lives in ``reachy_lib/`` (a subfolder, so the app never loads it as a tool); see its docstring.
"""
