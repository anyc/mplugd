#! /usr/bin/env python
# -*- coding: utf-8 -*-
#
# Author: Mario Kicherer (http://kicherer.org)
# License: GPL v2 (http://www.gnu.org/licenses/gpl-2.0.txt)
#
# This action calls (shell) scripts after (dis-)connect event from the
# corresponding folder
#

import Xlib.ext.randr as randr
import os, subprocess

connectdir="connect.d"
disconnectdir="disconnect.d"

def execute_script(mplugd, command):
	if not os.access(command[0], os.X_OK):
		if mplugd.verbose:
			print "Ignoring", command[0]
			return
	
	if mplugd.verbose:
		print "Executing script", command[0]
	
	subprocess.call(command)

def process(mplugd, event):
	if mplugd.verbose:
		print "Executing python script:", __name__
	
	connected = None
	
	# list of parameters that are passed to scripts
	command = ["filename", event.etype]
	if event.item:
		command.append(event.item.name)
	
	#
	# overwrite and add parameters with regard to event type
	#
	
	if event.etype == "OutputChangeNotify":
		command[2] = event.item.name
		if event.item.connection == randr.Disconnected and event.item.crtc != 0:
			connected = False
			command[1] = "OutputDisconnect"
		elif event.item.connection == randr.Connected and event.item.crtc == 0:
			connected = True
			command[1] = "OutputConnect"
		else:
			print "startscript error", event.item.connection, event.item.crtc
			return
	
	elif event.etype == "NewPlaybackStream":
		connected = True
		if event.item:
			command.append(getattr(event.item, "application.process.binary"))
	elif event.etype == "PlaybackStreamRemoved":
		connected = False
		if event.item:
			command.append(getattr(event.item, "application.process.binary"))
	else:
		if mplugd.verbose:
			print __name__, "unkown event, stopping"
			return
	
	# choose script directory
	if connected:
		directory = connectdir;
	else:
		directory = disconnectdir;
	
	# walk through directories and execute scripts
	for d in mplugd.config["action_directory"]:
		for root, dirs, files in os.walk(d+directory):
			files.sort()
			for filename in files:
				fullpath = os.path.join(root, filename)
				
				if fullpath.split(".")[-1] == "script":
					command[0] = fullpath
					execute_script(mplugd, command)