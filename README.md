
mplugd
======

mplugd is a daemon that listens on events (e.g. xrandr or pulseaudio) and
executes user-defined actions on certain events. In contrast to other
approaches, it listens to events by registering callback handlers *instead* of
polling and parsing tool output. Event processing is done through a threaded
producer/consumer architecture that can be extended by plugins to insert new
event types. Actions can be defined using INI-like rule files or simple
scripts.

A common use-case is automatic configuration of plugged-in devices like HDMI
or DisplayPort displays including switch of audio output using pulseaudio.

Requirements:

	* For pulseaudio: dbus-python
	* For X events: python-xlib (SVN revision > r160 or version > 0.15)

Usage
-----

1. Place your rules/scripts either into `/etc/mplugd/action.d/`,
   `~/mplugd/action.d/` or `$SRCDIR/mplugd/action.d/`. For examples, look into
   `mplugd/examples/action.d/`. Only files ending with `.py` or `.rules` are
   considered. You can loop-up the values for your current system using
   `mplugd -d`.
2. Start `mplugd`. In case you manually installed python-xlib, you might need
   to add its location to PYTHONPATH before starting mplugd.