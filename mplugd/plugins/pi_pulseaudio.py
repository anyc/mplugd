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
import header

mplugd = None
keywords = ["pa", "stream", "sink"]
eventloop = None

# convert byte array to string
def dbus2str(db):
	if type(db)==dbus.Struct:
		return tuple(dbus2str(i) for i in db)
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
	return ('type: %s'%type(db), db)

def dpprint(data, **kwargs):
	pprint(dbus2str(data), **kwargs)

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
				if exception.get_dbus_name() != 'org.freedesktop.DBus.Error.ServiceUnknown':
					raise
				print "Trying to start PA", exception
				Popen(['pulseaudio', '--start', '--log-target=syslog'], stdout=open('/dev/null', 'w'), stderr=STDOUT).wait()
				from time import sleep
				sleep(1)
				dbus_addr = False
		
		if mplugd.verbose:
			print "PA connecting to", dbus_addr
		
		self.bus = dbus.connection.Connection(dbus_addr)
		self.core = self.bus.get_object(object_path='/org/pulseaudio/core1')
	
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

# class for Pulseaudio events
class PAMP_Event(header.MP_Event):
	def __init__(self, eventloop, event, sender, path):
		super(PAMP_Event, self).__init__(event.get_member())
		self.eventloop = eventloop
		self.sender = sender
		self.event = event
		self.path = path
		
		self.item = self.get_event_item()
	
	def get_event_item(self):
		if self.event.get_member() == "NewPlaybackStream" or self.event.get_member() == "PlaybackStreamRemoved":
			# get additional info for the event's stream
			# required for disconnect events because we cannot query the
			# server for info afterwards
			newstreams = get_state_streams()
			if self.path in newstreams.keys():
				self.item = newstreams[self.path]
				return self.item
			elif self.path in mplugd.laststate["stream"].keys():
				self.item = mplugd.laststate["stream"][self.path]
				return self.item
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
		threading.Thread.__init__(self)
	
	def handler(self, path, sender=None, msg=None):
		self.queue.push(PAMP_Event(self, msg, sender, path))
	
	def run(self):
		if mplugd.verbose:
			print "Starting PADBUS"
		DBusGMainLoop(set_as_default=True)
		
		self.pa_wrapper = PADbusWrapper(True)
		self.pa_wrapper.initialize_pa_bus()
		
		# local callback handler
		def cb_handler(path, sender=None, msg=None):
			self.handler(path, sender, msg)
		
		self.pa_wrapper.bus.add_signal_receiver(cb_handler, message_keyword="msg")
		
		core1 = self.pa_wrapper.bus.get_object('org.PulseAudio.Core1', '/org/pulseaudio/core1')
		core1.ListenForSignal('org.PulseAudio.Core1.NewPlaybackStream', dbus.Array(signature="o"))
		core1.ListenForSignal('org.PulseAudio.Core1.PlaybackStreamRemoved', dbus.Array(signature="o"))
		
		self.loop = gMainLoop()
		gthreads_init()
		ginit_threads()
		
		self.initflag.set()
		self.loop.run()

# internal representation of a sink
class Sink(object):
	keys = ["name", "Driver", "Index", "Volume",
		"Mute", "State", "Channels"]
	
	def __init__(self):
		self._data = None
		self._props = None
		self._pawrapper = None
	
	def cache_data(self):
		for k in self.keys:
			setattr(self, k, getattr(self, k))
	
	def __getattr__(self, attr):
		if attr == "name":
			return self.Name
		
		if self._props and attr in self._props:
			return self._props[attr][:-1]
		
		val = self._pawrapper.get_sink_attr(self._data, attr)
		if val:
			return val
		
		return ""
		
	def __str__(self):
		lst = {}
		
		for k in self.keys:
			if hasattr(self, k):
				lst[k] = getattr(self, k)
		
		for k,v in self._props.items():
			lst[k] = v[:-1]
		
		return pformat(lst, indent=5)

# internal representation of a stream
class Stream(object):
	keys = ["name", "Driver", "Index", "Volume",
		"Mute", "Channels"]
	
	def __init__(self):
		self._data = None
		self._props = None
		self._pawrapper = None
	
	def cache_data(self):
		for k in self.keys:
			setattr(self, k, getattr(self, k))
	
	def __getattr__(self, attr):
		if attr == "name" or attr == "Name":
			return self._props["application.name"][:-1]
		
		if self._props and attr in self._props:
			return self._props[attr][:-1]
		
		val = self._pawrapper.get_stream_attr(self._data, attr)
		if val:
			return val
		
		return ""
	
	def __str__(self):
		lst = {}
		
		for k in self.keys:
			if hasattr(self, k):
				lst[k] = getattr(self, k)
		
		for k,v in self._props.items():
			lst[k] = v[:-1]
		
		return pformat(lst, indent=5)

def get_state_sinks():
	dic = {}
	
	sinks = eventloop.pa_wrapper.get_sinks()
	if sinks:
		for sink in sinks.keys():
			s = Sink()
			s._data = sinks[sink]
			s._props = eventloop.pa_wrapper.get_sink_attr(sinks[sink], 'PropertyList')
			s._pawrapper = eventloop.pa_wrapper
			s.cache_data()
			
			dic[s.Name] = s
	return dic

def get_state_streams():
	dic = {}
	
	streams = eventloop.pa_wrapper.get_streams()
	if streams:
		for stream in streams.keys():
			s = Stream()
			s._data = streams[stream]
			s._props = eventloop.pa_wrapper.get_stream_attr(streams[stream], 'PropertyList')
			s._pawrapper = eventloop.pa_wrapper
			s.cache_data()
			
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
				return True
	
	elif pl[2] == "set" and pl[3] == "defaultsink":
		#true_pa_set_defaultsink_to_alsa.card_name=HDA Intel PCH
		# 0    1  2    3         4     5
		for k,v in state["sink"].items():
			if sparser.match(val, getattr(v, "_".join(pl[5:]))):
				if mplugd.verbose:
					print "set sink to", k
				eventloop.pa_wrapper.set_fallback_sink(v._data);
	
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
				for option_key,option_val in sparser.items(sc_section):
					for stream in state["stream"].values():
						if sparser.match(option_val, getattr(stream, option_key[7:])):
							if mplugd.verbose:
								print "move", "\"%s\"" % option_val, "to", k
							eventloop.pa_wrapper.move_stream2sink(stream._data, v._data)
	
	elif pl[3] == "event":
		#true_stream_move_event_to_alsa.card_name=HDA Intel PCH
		#  0     1     2    3    4   5
		for k,v in state["sink"].items():
			if sparser.match(val, getattr(v, "_".join(pl[5:]))):
				if mplugd.verbose:
					print "move \"%s\" to \"%s\"" % ( event.item.Name, k)
				eventloop.pa_wrapper.move_stream2sink(event.item._data, v._data)
				break
	else:
		print __name__, "unknown command", "_".join(pl), val

def initialize(main,queue):
	global mplugd
	global eventloop
	
	mplugd = main
	eventloop = PA_event_loop(queue)
	
	return eventloop
