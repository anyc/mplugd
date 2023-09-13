#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Author: Mario Kicherer (http://kicherer.org)
# License: GPL v2 (http://www.gnu.org/licenses/gpl-2.0.txt)
#
# Plugin that listens on udev events
#

from __future__ import absolute_import
from __future__ import print_function
import pyudev, sys, threading
from pprint import pprint, pformat

if __name__ == "__main__":
	sys.path.append("../")

from header import MP_Event, MP_object

mplugd = None
keywords = ["udev"]
eventloop = None

class Udev_object(MP_object):
	keys = ["name", "subsystem", "device_type", "sys_path"]
	
	def __init__(self, obj):
		MP_object.__init__(self, obj, self.get_attr);
	
	def get_attr(self, obj, attr):
		return None
	
	def __getattr__(self, attr):
		if attr == "name":
			return self._obj.sys_name
		
		if attr in list(self._obj.keys()):
			return self._obj[attr]
		if attr.upper() in list(self._obj.keys()):
			return self._obj[attr.upper()]
		
		if hasattr(self._obj, attr):
			return getattr(self._obj, attr)
		
		if attr in list(self._obj.attributes.keys()):
			return self._obj.attributes[attr]
		
		return MP_object.__getattr__(self, attr)
	
	def verbose_str(self):
		rep = self.getrepr()
		
		for attr in self._obj.keys():
			rep[attr.lower()] = self._obj[attr]
		
		for attr in self._obj.attributes.keys():
			try:
				rep[attr] = self._obj.attributes[attr]
			except KeyError:
				# somehow it contains keys that don't exist o.O
				pass
		
		return pformat(rep, indent=5)

class Udev_Event(MP_Event):
	def __init__(self, eventloop, action, device):
		super(Udev_Event, self).__init__("Udev%s%s" % (action[0].upper(),action[1:]))
		self.eventloop = eventloop
		self.item = self.get_item(device)
	
	def get_item(self, device):
		return Udev_object(device)
	
	def __str__(self):
		return "<Event %s etype=%s name=\"%s\">" %(self.__class__.__name__, self.etype, self.item.name)

# main event loop thread of this plugin
class Udev_event_loop(object):
	def __init__(self, queue):
		self.queue = queue
		self.stop = False
		self.initflag = threading.Event()
		self.handler = self.event_handler
	
	def event_handler(self, action, device):
		#print action, device
		self.queue.push(Udev_Event(self, action, device))
	
	def start(self):
		self.context = pyudev.Context()
		
		self.monitor = pyudev.Monitor.from_netlink(self.context)
		
		self.observer = pyudev.MonitorObserver(self.monitor, self.handler)
		self.observer.start()
		
		self.initflag.set()

def handle_rule_condition(sparser, pl, values, state, event):
	if pl[2] == "device":
		#if_udev_device_block_name=dm-0
		# 0   1    2      3    4
		
		for device in eventloop.context.list_devices(subsystem=pl[3]):
			dev = Udev_object(device)
			#print device
			if dev.name in values:
				return (False, True)
		if mplugd.verbose:
			print("no such device")
		return (False, False)
	
	# (ignore, valid)
	return (True, False)

def get_state(state):
	pass

def shutdown():
	eventloop.observer.stop()

def join():
	pass

def initialize(main,queue):
	global mplugd
	global eventloop
	
	mplugd = main
	
	eventloop = Udev_event_loop(queue)
	
	return eventloop

def dump_state(state):
	if "output" in state:
		print("Udev")
		print("")
		print("Please execute \"pi_udev.py list\" for a complete list of devices.")

if __name__ == "__main__":
	if len(sys.argv) == 1:
		print("Usage: ", sys.argv[0], "<listen|list [path]>")
		sys.exit(0)
	
	def event_handler(action, device):
		#print "Event: ", action, device
		e = Udev_Event(eventloop, action, device)
		print("Udev%s%s" % (action[0].upper(),action[1:]), e.item.subsystem, e.item.name, e.item.verbose_str())
	
	eventloop = Udev_event_loop(None)
	eventloop.handler = event_handler
	
	# workaround
	mplugd = eventloop
	mplugd.verbose = False
	
	eventloop.start()
	eventloop.initflag.wait()
	
	if len(sys.argv) == 2 and sys.argv[1] == "list":
		for device in eventloop.context.list_devices():
			print(device)
		shutdown()
		sys.exit(0)
	
	if len(sys.argv) == 3 and sys.argv[1] == "list":
		dev = None
		try:
			dev = pyudev.Device.from_path(eventloop.context, sys.argv[2])
		except AttributeError:
			pass
		except pyudev.device.DeviceNotFoundAtPathError:
			pass
		except:
			print("Unexpected error:", sys.exc_info()[0])
		
		try:
			dev = pyudev.Device.from_device_file(eventloop.context, sys.argv[2])
		except ValueError:
			pass
		except:
			print("Unexpected error:", sys.exc_info()[0])
		
		if dev == None:
			print(sys.argv[2], "not found")
			shutdown()
			sys.exit(0)
		
		print(Udev_object(dev).verbose_str())
	
	if sys.argv[1] == "listen":
		print("Waiting for udev events...")
		import time
		while True:
			try:
				time.sleep(1)
			except KeyboardInterrupt:
				shutdown()
				sys.exit(0)