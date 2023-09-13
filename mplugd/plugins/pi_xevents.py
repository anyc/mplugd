#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Author: Mario Kicherer (http://kicherer.org)
# License: GPL v2 (http://www.gnu.org/licenses/gpl-2.0.txt)
#
# Plugin that listens for X events
#

from __future__ import absolute_import
from __future__ import print_function
import Xlib, Xlib.display, Xlib.ext.randr as randr
import edid, threading
from pprint import pprint, pformat
import header
from six.moves import map
from six.moves import range

mplugd = None
keywords = ["output"]
eventloop = None

# internal representation of a X output device
class Output(object):
	def __init__(self):
		self._data = None
		self._edid = None
	
	def __getattr__(self, attr):
		# connection = 0 -> connected = 1, connection=2 -> unknown
		if attr == "connected":
			if self._data.connection == 2:
				return 2
			else:
				return 1 - self._data.connection
		
		if hasattr(self._data, attr):
			return getattr(self._data, attr)
		if self._edid and hasattr(self._edid, attr):
			return getattr(self._edid, attr)
		return ""
	
	def __str__(self):
		lst = {}
		
		# keys we will show during a dump
		keys = ["name", "connected", "model_name", "id_string","crtc",
			"mm_width","mm_height","subpixel_order","crtcs",
			"modes", "clones", "serial_number", "date", "video_input_def",
			"size", "gamma", "feature_support", "color_characteristics",
			"timings", "range_dt", "timing_dt", "monitor_details"]
		
		for k in keys:
			lst[k] = getattr(self, k)
		
		return pformat(lst, indent=5)

# query the edid module for output_nr
def get_edid(display, output_nr):
	PROPERTY_EDID = 76
	INT_TYPE = 19
	
	props = display.xrandr_list_output_properties(output_nr)
	if PROPERTY_EDID in props.atoms:
		try:
			rawedid = display.xrandr_get_output_property(output_nr, PROPERTY_EDID, INT_TYPE, 0, 400)
		except:
			print("error loading EDID data of output", output_nr)
			return None
		edidstream = rawedid._data['value']
		e2 = ''.join(map(chr, edidstream))
		e = edid.Edid(e2)
		
		return e
	else:
		return None

# X event class
class XMP_Event(header.MP_Event):
	def __init__(self, eventloop, event):
		super(XMP_Event, self).__init__(event.__class__.__name__)
		self.event = event
		self.eventloop = eventloop
		self.item = self.get_event_item()
	
	# process the "raw" event from Xorg and set self.item to the item in question
	def get_event_item(self):
		if self.etype == "OutputChangeNotify":
			# get additional info for the event's output
			# required for disconnect events because we cannot query the
			# server for info afterwards
			newoutputs = get_state_outputs()
			if self.event.output in list(newoutputs.keys()):
				self.item = newoutputs[self.event.output]
			elif self.event.output in list(mplugd.laststate["output"].keys()):
				self.item = mplugd.laststate["output"][self.event.output]
			else:
				print("Did not find information on output", self.event.output)
			
			if (not self.item._edid or not self.item._edid.valid) and self.event.output in list(mplugd.laststate["output"].keys()):
				self.item._edid = mplugd.laststate["output"][self.event.output]._edid
			
			return self.item
		
		return None

# main event loop thread of this plugin
class X_event_loop(threading.Thread):
	def __init__(self, queue):
		self.queue = queue
		self.stop = False
		self.initflag = threading.Event()
		self.xlock = threading.Lock()
		threading.Thread.__init__(self)
	
	def run(self):
		self.xlock.acquire()
		# get X objects
		self.display = Xlib.display.Display(':0')
		display = self.display
		self.root = display.screen().root
		root = self.root

		if not display.has_extension("RANDR"):
			print("RANDR extension not found")
			sys.exit(1)

		display.query_extension('RANDR')
		if mplugd.verbose:
			r = display.xrandr_query_version()
			print("RANDR extension version %d.%d" % (r.major_version, r.minor_version))

		# set which types of events we want to receive
		root.xrandr_select_input(
			randr.RRScreenChangeNotifyMask
			| randr.RRCrtcChangeNotifyMask
			| randr.RROutputChangeNotifyMask
			| randr.RROutputPropertyNotifyMask
			)
		
		self.xlock.release()
		self.initflag.set()
		
		import time
		# enter event loop
		while not self.stop:
			for x in range(0, self.root.display.pending_events()):
				e = self.root.display.next_event()
				mp_ev = XMP_Event(self, e)
				self.queue.push(mp_ev)
			
			# TODO find something better
			time.sleep(1)
			
			## other randr events
			#if e.__class__.__name__ == randr.ScreenChangeNotify.__name__:
			#if e.__class__.__name__ == randr.CrtcChangeNotify.__name__:
			#if e.__class__.__name__ == randr.OutputPropertyNotify.__name__:
			#if e.__class__.__name__ == randr.OutputChangeNotify.__name__:

# get current list of outputs and create internal Output objects
def get_state_outputs():
	eventloop.xlock.acquire()
	resources = eventloop.root.xrandr_get_screen_resources()._data
	
	dic = {}
	for idx in resources["outputs"]:
		o = Output()
		o._data = eventloop.display.xrandr_get_output_info(idx, resources['config_timestamp'])
		o._edid = get_edid(eventloop.display, idx)
		
		#state["outputs"][o.name] = o
		dic[idx] = o
	
	eventloop.xlock.release()
	
	return dic

def get_state(state):
	state["output"] = get_state_outputs()

def dump_state(state):
	if "output" in state:
		print("Xorg")
		print("")
		for k,v in state["output"].items():
			print(v.name, "(ID: %s)" % k)
			print(str(v))

def shutdown():
	eventloop.stop = True

def join():
	eventloop.join()

def initialize(main,queue):
	global mplugd
	global eventloop
	
	mplugd = main
	
	if int(Xlib.__version__[0]) == 0 and int(Xlib.__version__[1]) <= 15 and not hasattr(Xlib.display.Display, "extension_add_subevent"):
		print("Require at least python-xlib SVN revision > r160 or version > 0.15. Your version:", Xlib.__version_string__)
		return None
	
	eventloop = X_event_loop(queue)
	
	return eventloop
