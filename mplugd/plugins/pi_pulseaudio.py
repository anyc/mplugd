#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Author: Mario Kicherer (http://kicherer.org)
# License: GPL v2 (http://www.gnu.org/licenses/gpl-2.0.txt)
#
# Plugin that listens for PulseAudio events
#

import os, sys, dbus, threading
from pprint import pprint

from dbus.mainloop.glib import DBusGMainLoop
from gobject import MainLoop as gMainLoop, threads_init as gthreads_init
from dbus.glib import init_threads as ginit_threads
from pprint import pprint, pformat

if __name__ == "__main__":
	sys.path.append("../")

from header import MP_Event, MP_object

mplugd = None
keywords = ["pa", "stream", "sink"]
eventloop = None

# convert byte array to string
def dbus2str(db):
	if type(db)==dbus.Struct:
		return str(tuple(dbus2str(i) for i in db))
	if type(db)==dbus.Array:
		return "".join([dbus2str(i) for i in db])
	if type(db)==dbus.Dictionary:
		return dict((dbus2str(key), dbus2str(value)) for key, value in db.items())
	if type(db)==dbus.String:
		return db+''
	if type(db)==dbus.UInt32:
		return str(db+0)
	if type(db)==dbus.Byte:
		return chr(db)
	if type(db)==dbus.Boolean:
		return db==True
	if type(db)==dict:
		return dict((dbus2str(key), dbus2str(value)) for key, value in db.items())
	return "(%s:%s)" % (type(db), db)

def dpprint(data, **kwargs):
	pprint(dbus2str(data), **kwargs)

# DBus wrapper class for PA
class PADbusWrapper(object):
	def __init__(self, verbose):
		self.bus = None
		self.verbose = verbose
		self.core = None
	
	# connect to PA's DBUS
	def initialize_pa_bus(self):
		dbus_addr = False
		while not dbus_addr:
			try:
				_sbus = dbus.SessionBus()
				
				dbus_addr = os.environ.get('PULSE_DBUS_SERVER')
				if not dbus_addr:
					dbus_addr = _sbus.get_object('org.PulseAudio1', '/org/pulseaudio/server_lookup1').Get('org.PulseAudio.ServerLookup1', 'Address', dbus_interface='org.freedesktop.DBus.Properties')
			
			except dbus.exceptions.DBusException as exception:
				#if exception.get_dbus_name() != 'org.freedesktop.DBus.Error.ServiceUnknown':
					#raise
				print "Could not connect to PA: ", exception
				return
				#import subprocess
				#subprocess.Popen(['pulseaudio', '--start', '--log-target=syslog'], stdout=open('/dev/null', 'w'), stderr=subprocess.STDOUT).wait()
				#from time import sleep
				#sleep(1)
				#dbus_addr = False
		
		if mplugd.verbose:
			print "PA connecting to", dbus_addr
		
		self.bus = dbus.connection.Connection(dbus_addr)
		
		# get PA's core object
		self.core = self.bus.get_object(object_path='/org/pulseaudio/core1')
		# get the stream restore database
		self.ext_restore = dbus.Interface( self.bus.get_object(object_path="/org/pulseaudio/stream_restore1"), dbus_interface='org.freedesktop.DBus.Properties' )
		
	
	def get_ports(self, sink):
		return [ (path, dbus.Interface( self.bus.get_object(object_path=path), dbus_interface='org.freedesktop.DBus.Properties' )) for path in sink.Get('org.PulseAudio.Core1.Device', "Ports") ]
	
	def get_port_attr(self, port, attr):
		return dbus2str(port.Get('org.PulseAudio.Core1.DevicePort', attr))
	
	def get_sinks(self):
		sinks = ( dbus.Interface( self.bus.get_object(object_path=path), dbus_interface='org.freedesktop.DBus.Properties' ) for path in 
				self.core.Get('org.PulseAudio.Core1', 'Sinks', dbus_interface='org.freedesktop.DBus.Properties' ) )
		
		sinks = dict((sink.Get('org.PulseAudio.Core1.Device', 'Name'), sink) for sink in sinks)
		return sinks
	
	def get_sink_attr(self, sink, attr):
		return dbus2str(sink.Get('org.PulseAudio.Core1.Device', attr))
	
	def get_streams(self):
		pstreams = ( dbus.Interface( self.bus.get_object(object_path=path), dbus_interface='org.freedesktop.DBus.Properties' ) for path in 
				self.core.Get('org.PulseAudio.Core1', 'PlaybackStreams', dbus_interface='org.freedesktop.DBus.Properties' ) )
		
		pstreams = dict((pstream.Get('org.PulseAudio.Core1.Stream', 'Index'), pstream) for pstream in pstreams)
		
		return pstreams
	
	def get_stream_attr(self, stream, attr):
		return dbus2str(stream.Get('org.PulseAudio.Core1.Stream', attr))
	
	def move_stream2sink(self, stream, sink):
		move = stream.get_dbus_method('Move', 'org.PulseAudio.Core1.Stream')
		
		move(sink)
	
	def set_fallback_sink(self, sink):
		self.core.Set('org.PulseAudio.Core1', 'FallbackSink', sink, signature="ssv")
	
	def get_restore_entries(self):
		entries = ( dbus.Interface( self.bus.get_object(object_path=path), dbus_interface='org.freedesktop.DBus.Properties' ) for path in 
		   self.ext_restore.Get('org.PulseAudio.Ext.StreamRestore1', 'Entries', dbus_interface='org.freedesktop.DBus.Properties' ) )
		
		entries = [(entry.Get('org.PulseAudio.Ext.StreamRestore1.RestoreEntry', 'Name'), entry) for entry in entries]
		return entries
	
	def set_restore_entry(self, entry, device):
		entry.Set('org.PulseAudio.Ext.StreamRestore1.RestoreEntry', 'Device', device)
		#entries = self.get_restore_entries()
		
		#found = False
		#for e in entries:
			#ename = e.Get('org.PulseAudio.Ext.StreamRestore1.RestoreEntry', 'Name')
			##edev = e.Get('org.PulseAudio.Ext.StreamRestore1.RestoreEntry', 'Device')
			
			#if str(ename) == "sink-input-by-application-name:%s" % name or \
					#str(ename) == "sink-input-by-application-name: ALSA plug-in [%s]" % name:
				##e.Set('org.PulseAudio.Ext.StreamRestore1.RestoreEntry', 'Device', "alsa_output.pci-0000_01_00.1.hdmi-stereo")
				##e.Set('org.PulseAudio.Ext.StreamRestore1.RestoreEntry', 'Device', "alsa_output.pci-0000_00_1b.0.analog-stereo")
				##print "set", name, "to", device
				#e.Set('org.PulseAudio.Ext.StreamRestore1.RestoreEntry', 'Device', device)
				#found = True
		
		#if not found:
			#print "set_restore_entry: no entry found for", name
	
	def __getattr__(self, attr):
		if hasattr(self, "get_%s" % attr):
			return getattr(self, "get_%s" % attr)()
		
		spl = attr.split("_")
		if spl[0] == "get" and spl[1] == "sink":
			#'PropertyList'
			return self.get_sink_attr(spl[2:])
		if spl[0] == "get" and spl[1] == "stream":
			#'PropertyList'
			return self.get_stream_attr(spl[2:])
		
		print "error", attr
		raise AttributeError

# Pulseaudio event class
class PAMP_Event(MP_Event):
	def __init__(self, eventloop, event, sender, path):
		super(PAMP_Event, self).__init__(event.get_member())
		self.eventloop = eventloop
		self.sender = sender
		self.event = event
		self.path = path
		
		self.item = None
		self.get_event_item()
	
	# process the "raw" event from DBUS and set self.item to the item in question
	def get_event_item(self):
		if self.event.get_member() == "ActivePortUpdated":
			if not str(self.event.get_path()) in mplugd.laststate["sink"]:
				# TODO source events, we only handle sinks for now
				self.ignore = True
				return
			
			if self.path in mplugd.laststate["sink"][str(self.event.get_path())].ports:
				self.item = mplugd.laststate["sink"][str(self.event.get_path())].ports[self.path]
			else:
				print "unknown port:", self.path
		
		if self.event.get_member() == "NewPlaybackStream" or self.event.get_member() == "PlaybackStreamRemoved":
			# get additional info for the event's stream
			# required for disconnect events because we cannot query the
			# server for info afterwards
			newstreams = get_state_streams()
			if self.path in newstreams.keys():
				self.item = newstreams[self.path]
			elif self.path in mplugd.laststate["stream"].keys():
				self.item = mplugd.laststate["stream"][self.path]
			else:
				print "Did not find information on stream", self.path, newstreams
	
	def __str__(self):
		return "<Event %s etype=%s path=%s>" %(self.__class__.__name__, self.etype, self.path)

# main event loop thread for this plugin
class PA_event_loop(threading.Thread):
	def __init__(self, queue):
		self.queue = queue
		self.pa_wrapper = None
		self.initflag = threading.Event()
		self.loop = None
		threading.Thread.__init__(self)
	
	# push event into main queue
	def handler(self, path, sender=None, msg=None):
		self.queue.push(PAMP_Event(self, msg, sender, path))
	
	def run(self):
		DBusGMainLoop(set_as_default=True)
		
		self.pa_wrapper = PADbusWrapper(True)
		self.pa_wrapper.initialize_pa_bus()
		
		if not self.pa_wrapper.bus:
			self.initflag.set()
			return
		
		# local callback handler
		def cb_handler(path=None, sender=None, msg=None):
			self.handler(path, sender, msg)
		
		self.pa_wrapper.bus.add_signal_receiver(cb_handler, message_keyword="msg")
		
		core1 = self.pa_wrapper.bus.get_object('org.PulseAudio.Core1', '/org/pulseaudio/core1')
		core1.ListenForSignal('org.PulseAudio.Core1.NewPlaybackStream', dbus.Array(signature="o"))
		core1.ListenForSignal('org.PulseAudio.Core1.PlaybackStreamRemoved', dbus.Array(signature="o"))
		
		core1.ListenForSignal('org.PulseAudio.Core1.Device.ActivePortUpdated', dbus.Array(signature="o"))
		
		self.loop = gMainLoop()
		gthreads_init()
		ginit_threads()
		
		self.initflag.set()
		self.loop.run()

class PA_object(MP_object):
	def __init__(self, dbus_obj, pawrapper, get_attr):
		MP_object.__init__(self, dbus_obj, get_attr);
		self._props = None
		self._pawrapper = pawrapper
	
	def __getattr__(self, attr):
		if attr == "name":
			return self.Name
		
		# check if attribute is in the property dictionary
		if self._props and attr in self._props:
			return self._props[attr][:-1]
		
		return MP_object.__getattr__(self, attr)
	
	# __str__ helper
	def getrepr(self):
		lst = {}
		
		lst.update(MP_object.getrepr(self))
		
		if self._props:
			for k,v in self._props.items():
				lst[k] = v[:-1]
		return lst

# internal representation of a sink
class Sink(PA_object):
	keys = ["Name", "Driver", "Index", "Volume",
		"Mute", "State", "Channels", "ActivePort"]
	
	def __init__(self, dbus_obj, pawrapper):
		PA_object.__init__(self, dbus_obj, pawrapper, pawrapper.get_sink_attr);
		self._props = self.get_attr(dbus_obj, 'PropertyList')
		
		# get the list of ports for this device
		self._port_objs = eventloop.pa_wrapper.get_ports(self._obj)
		self.ports = {}
		for path,pobj in self._port_objs:
			p = Port(pobj, pawrapper, self)
			p.cache_obj()
			self.ports[str(pobj.object_path)] = p
	
	def __str__(self):
		lst = PA_object.getrepr(self)
		lst["ports"] = {}
		for k,v in self.ports.items():
			lst["ports"][k] = v.getrepr()
		return pformat(lst, indent=5)

# internal representation of a stream
class Stream(PA_object):
	keys = ["Name", "Driver", "Index", "Volume",
		"Mute", "Channels"]
	
	def __init__(self, dbus_obj, pawrapper):
		PA_object.__init__(self, dbus_obj, pawrapper, pawrapper.get_stream_attr);
		self._props = self.get_attr(dbus_obj, 'PropertyList')
	
	def __getattr__(self, attr):
		if attr == "name" or attr == "Name":
			return self._props["application.name"][:-1]
		
		return PA_object.__getattr__(self, attr)

# internal representation of a sink
class Port(PA_object):
	keys = ["Name", "Description", "Priority"]
	
	def __init__(self, dbus_obj, pawrapper, device):
		PA_object.__init__(self, dbus_obj, pawrapper, pawrapper.get_port_attr);
		self.device = device
	
	def __getattr__(self, attr):
		if attr == "device":
			return self.device
		
		return PA_object.__getattr__(self, attr)

# query PA for a list of sinks
def get_state_sinks():
	dic = {}
	
	sinks = eventloop.pa_wrapper.get_sinks()
	if sinks:
		for sink in sinks.keys():
			s = Sink(sinks[sink], eventloop.pa_wrapper)
			s.cache_obj()
			
			dic[sinks[sink].object_path] = s
	return dic

# query PA for a list of streams
def get_state_streams():
	dic = {}
	
	streams = eventloop.pa_wrapper.get_streams()
	if streams:
		for stream in streams.keys():
			s = Stream(streams[stream], eventloop.pa_wrapper)
			s.cache_obj()
			
			dic[streams[stream].object_path] = s
	return dic

def get_state(state):
	state["sink"] = get_state_sinks()
	state["stream"] = get_state_streams()

def shutdown():
	eventloop.loop.quit()

def join():
	eventloop.join()

# process rules that contain plugin-specific code
def handle_rule_cmd(sparser, pl, val, state, event):
	if pl[0] == "on" and pl[1] == "stream":
		#on_stream_class
		# 0   1      2
		sc_section = "stream_class %s" % val[0]
		if not sparser.has_section(sc_section):
			if mplugd.verbose:
				print "Section [stream_class %s] not found" % val[0]
			return False
		
		for k,v in sparser.items(sc_section):
			if sparser.match(v, getattr(event.item, k[7:])):
				if mplugd.verbose:
					print "match"
				return True
	
	elif pl[2] == "set" and pl[3] == "defaultsink":
		#true_pa_set_defaultsink_to_alsa.card_name=HDA Intel PCH
		# 0    1  2    3         4     5
		for k,v in state["sink"].items():
			if sparser.match(val, getattr(v, "_".join(pl[5:]))):
				if mplugd.verbose:
					print "set sink to", k
				eventloop.pa_wrapper.set_fallback_sink(v._obj);
	
	elif pl[3] == "class":
		#true_stream_move_class_asd_to_alsa.card_name=HDA NVidia
		#  0    1     2     3    4   5   6
		sc_section = "stream_class %s" % pl[4]
		if not sparser.has_section(sc_section):
			if mplugd.verbose:
				print "Section [stream_class %s] not found" % pl[4]
			return
		
		for k,v in state["sink"].items():
			if sparser.match(val, getattr(v, "_".join(pl[6:]))):
				rentries = eventloop.pa_wrapper.get_restore_entries()
				
				for option_key,option_val in sparser.items(sc_section):
					# set restore entry for new streams
					for name, entry in rentries:
						match = sparser.getmatch(option_val, name, "sink-input-by-%s:" % option_key[7:].replace(".", "-"))
						if match != None:
							if mplugd.verbose:
								print "set restore entry of", "\"%s\"" % name, "to", v.name
							eventloop.pa_wrapper.set_restore_entry(entry, v.name)
					
					# switch running streams
					for stream in state["stream"].values():
						if not hasattr(stream, option_key[7:]):
							continue
						if sparser.match(option_val, getattr(stream, option_key[7:])):
							if mplugd.verbose:
								print "move", "\"%s\"" % option_val, "to", k
							eventloop.pa_wrapper.move_stream2sink(stream._obj, v._obj)
	
	elif pl[3] == "event":
		#true_stream_move_event_to_alsa.card_name=HDA Intel PCH
		#  0     1     2    3    4   5
		for k,v in state["sink"].items():
			if sparser.match(val, getattr(v, "_".join(pl[5:]))):
				if mplugd.verbose:
					print "move \"%s\" to \"%s\"" % ( event.item.Name, k)
				eventloop.pa_wrapper.move_stream2sink(event.item._obj, v._obj)
				break
	else:
		print __name__, "unknown command", "_".join(pl), val

def dump_state(state):
	print "PulseAudio:"
	
	if "sink" in state:
		for k,v in state["sink"].items():
			print ""
			print getattr(v, "alsa.card_name"), "(ID: %s)" % k
			print str(v)
	
	if "stream" in state:
		for k,v in state["stream"].items():
			print ""
			print v.name, "(ID: %s)" % k
			print str(v)

def initialize(main,queue):
	global mplugd
	global eventloop
	
	mplugd = main
	eventloop = PA_event_loop(queue)
	
	return eventloop

if __name__ == "__main__":
	def printhandler(path, sender=None, msg=None):
		print "Event: ", path, sender, msg
	
	eventloop = PA_event_loop(None)
	eventloop.handler = printhandler
	
	# workaround
	mplugd = eventloop
	mplugd.verbose = False
	
	eventloop.start()
	eventloop.initflag.wait()
	
	if not eventloop.loop:
		sys.exit(1)
	
	state = {}
	get_state(state)
	
	#print state
	
	
	ext_restore = dbus.Interface( eventloop.pa_wrapper.bus.get_object(object_path="/org/pulseaudio/stream_restore1"), dbus_interface='org.freedesktop.DBus.Properties' )
	
	entries = ( dbus.Interface( eventloop.pa_wrapper.bus.get_object(object_path=path), dbus_interface='org.freedesktop.DBus.Properties' ) for path in 
		ext_restore.Get('org.PulseAudio.Ext.StreamRestore1', 'Entries', dbus_interface='org.freedesktop.DBus.Properties' ) )
	
	for e in entries:
		name = e.Get('org.PulseAudio.Ext.StreamRestore1.RestoreEntry', 'Name'),
		dev = e.Get('org.PulseAudio.Ext.StreamRestore1.RestoreEntry', 'Device')
		
		print str(name[0]), "--", dev
	
	shutdown()
	