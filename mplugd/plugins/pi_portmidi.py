#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Author: Mario Kicherer (http://kicherer.org)
# License: GPL v2 (http://www.gnu.org/licenses/gpl-2.0.txt)
#
# MIDI plugin - react on MIDI input and send commands to MIDI devices
#

import pyportmidi as pm
import time, threading, sys, re

if __name__ == "__main__":
	sys.path.append("../")

from header import MP_Event,MP_object

mplugd=None
eventloop=None
keywords = ["portmidi"]
outputs=[]
inputs=[]

class Midi_object(MP_object):
	keys = ["name", "cmd", "device"]
	
	def __init__(self, cmd, device):
		MP_object.__init__(self, None, None);
		self.cmd = cmd[0]
		self.time = cmd[1]
		self.device = device
	
	def __getattr__(self, attr):
		if attr == "name":
			return self.device["name"]
		
		if attr == "command":
			return "%x" % self.cmd[0]
		
		if attr == "values":
			return " ".join([ "%x" % c for c in self.cmd[1:]])
		
		return MP_object.__getattr__(self, attr)

class PM_Event(MP_Event):
	def __init__(self, eventloop, device, event):
		title = "MidiEvent"
		self.event = event
		if event[0][0] == 0x90:
			title = "MidiNoteOn"
		if event[0][0] == 0xb0:
			title = "MidiController"
		
		super(PM_Event, self).__init__(title)
		self.eventloop = eventloop
		self.item = Midi_object(event, device);
	
	def __str__(self):
		return "<Event %s etype=%s cmd=%s>" %(self.__class__.__name__, self.etype, self.event[0])

class PM_event_loop(threading.Thread):
	def __init__(self, queue):
		global inputs
		global outputs
		
		self.queue = queue
		self.stop = False
		self.initflag = threading.Event()
		threading.Thread.__init__(self)
		
		pm.init()
		
		for i in range(0,pm.get_count()):
			dev = {}
			dev["info"] = pm.get_device_info(i)
			dev["name"] = dev["info"][1]
			dev["input"] = dev["info"][2]
			
			if dev["input"] == 1:
				dev["obj"] = pm.Input(i)
				inputs.append(dev)
			else:
				dev["obj"] = pm.Output(i)
				outputs.append(dev)
		
		self.initflag.set()
	
	def run(self):
		while not self.stop:
			for i in inputs:
				dev = i["obj"]
				while dev.poll():
					cmds = dev.read(5);
					if len(cmds) > 0:
						if self.queue:
							for c in cmds:
								pm_ev = PM_Event(self, i, c)
								self.queue.push(pm_ev)
						else:
							print cmds
			try:
				time.sleep(0.1)
			except:
				break

def handle_rule_cmd(sparser, pl, val, state, event):
	if pl[1] != "portmidi":
		return
	
	if pl[2] == "send":
		for o in outputs:
			if o["name"] == pl[3]:
				# convert 3 hex strings into integers and send to midi device
				res = re.search("([\d\w]+)\s+([\d\w]+)\s+([\d\w]+)", val[0])
				if res:
					l=[0,0,0]
					for i in range(1,4):
						l[i-1] = int(res.group(i), 16)
					
					if mplugd.verbose:
						print "MIDI sending %x %x %x" % (l[0], l[1], l[2])
					o["obj"].write_short(l[0], l[1], l[2]);
				else:
					print "unknown MIDI command: %s" % val

def initialize(main,queue):
	global mplugd
	global eventloop
	
	mplugd = main
	eventloop = PM_event_loop(queue)
	
	return eventloop

def shutdown():
	eventloop.stop = True
	eventloop.join()
	
	# causes segfault !?
	#for i in inputs:
		#i["obj"].close()
	#for o in outputs:
		#o["obj"].close()
	pm.quit()

def join():
	eventloop.join()

def get_state(state):
	#global eventloop
	
	#eventloop = PM_event_loop(None)
	
	#state["portmidi"] = inputs
	state["portmidi"] = outputs

def dump_state(state):
	print "PortMIDI\n"
	
	print "Inputs:"
	for i in inputs:
		print "\t",i["name"]
		
	print "Outputs:"
	for i in outputs:
		print "\t",i["name"]

if __name__ == "__main__":
	eventloop = PM_event_loop(None)
	eventloop.start()
	
	while True:
		try:
			time.sleep(1)
		except KeyboardInterrupt:
			shutdown()
			sys.exit(0)