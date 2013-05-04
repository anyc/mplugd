
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

Current list of event types
---------------------------

* New/removed Xorg displays
* Applications starting/ending audio output through PulseAudio
* PulseAudio port changes (e.g., plugged-in headphones)

Usage
-----

1. Place your rules/scripts either into `/etc/mplugd/action.d/`,
   `~/mplugd/action.d/` or `$SRCDIR/mplugd/action.d/`. For examples, look into
   `mplugd/examples/action.d/`. Only files ending with `.py` or `.rules` are
   considered. You can loop-up the values for your current system using
   `mplugd -d`.
2. Start `mplugd`. In case you manually installed python-xlib, you might need
   to add its location to PYTHONPATH before starting mplugd.

Rules example
-------------

* If DP-[0-9] gets connected to a display, change default sink to the sink
known as "HDA NVidia" card to ALSA and set the display configuration to
automatic.

		[rule on_dpX_connect]
		on_type=OutputChangeNotify
		on_name*=DP-[0-9]
		on_connected=1
		on_crtc=0
		true_stream_set_defaultsink_to_alsa.card_name=HDA NVidia
		true_exec=xrandr --output %event_name% --auto

* If a process with the binary `mplayer` starts audio output and if output DP-0
is connected, move this stream to sink "HDA NVidia", display a message in
the console and send a notification to the desktop.

		[rule move_new_mplayer_to_intel]
		on_type=NewPlaybackStream
		on_application.process.binary=mplayer
		if_output_DP-0_connected=1
		true_stream_move_event_to_alsa.card_name=HDA NVidia
		true_exec=echo "moving mplayer to HDA NVidia"
		true_exec=notify-send "mplugd moves mplayer to HDA NVidia"
