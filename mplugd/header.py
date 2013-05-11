#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Author: Mario Kicherer (http://kicherer.org)
# License: GPL v2 (http://www.gnu.org/licenses/gpl-2.0.txt)
#
# Some common code for mplugd
#

import threading, re, os, __init__
from pprint import pprint, pformat

mplugd = None
default_config = {
		"configfiles": ["/etc/mplugd/mplugd.conf", "~/.mplugd/mplugd.conf", os.path.dirname(__file__)+"/mplugd.conf"],
		"plugin_directory": [os.path.dirname(__file__)+"/plugins", "/etc/mplugd/plugins", "~/.mplugd/plugins"],
		"action_directory": [os.path.dirname(__file__)+"/action.d", "/etc/mplugd/action.d", "~/.mplugd/action.d"],
		"verbose": False
	}

# main class for mplugd
class MPlugD(object):
	def __init__(self):
		self.config = default_config
		self.laststate = None
		
		for conf in default_config["configfiles"]:
			self.read_config(conf)
	
	# read a INI-like config file
	def read_config(self, configfile):
		configfile = os.path.expanduser(configfile)
		if os.path.exists(configfile):
			if self.verbose:
				print "Loading config file %s" % configfile
			
			f = open(configfile)
			lines = f.readlines();
			for line in lines:
				res = re.match(r"\s*([\w\.]+)\s*([\+]*=)\s*(.*)\s*", line);
				if res:
					key = res.group(1);
					op = res.group(2)
					value = res.group(3);
					
					key = key.split(".");
					k = -1;
					itr = self.config;
					for k in range(0,len(key)-1):
						if not key[k] in itr:
							itr[key[k]] = {};
						itr = itr[key[k]];
					if op == "+=" and key[k+1] in itr:
						#if not value.strip() in itr[key[k+1]]:
						itr[key[k+1]].append(value.strip());
					else:
						itr[key[k+1]] = value.strip();
			f.close();
	
	def __getattr__(self, attr):
		if attr in self.config:
			if attr == "verbose":
				return self.config[attr] == "1" or self.config[attr] == "True"
			else:
				return self.config[attr]
		else:
			raise AttributeError

# root class for events
class MP_Event(object):
	def __init__(self, etype):
		self.eventloop = None # the event loop who created this event
		self.item = None # the item which this event is about
		self.etype = etype # the type of event
		
		# sometimes we get events that we're not interested in, this flag
		# allows to "drop" a event during processing
		self.ignore = False
	
	def __str__(self):
		return "<Event %s etype=%s>" %(self.__class__.__name__, self.etype)

# the main event queue, handles synchronization itself
class EventQueue(object):
	def __init__(self):
		self.items = []
		self.cond = threading.Condition()
		self.dostop = False
	
	def stop(self):
		self.dostop = True
	
	def push(self, obj):
		if self.dostop:
			return
		
		self.cond.acquire()
		self.items.append(obj)
		self.cond.notify()
		self.cond.release()
	
	def pop(self):
		self.cond.acquire()
		while len(self.items) == 0 and not self.dostop:
			self.cond.wait(1)
		
		if len(self.items) == 0 and self.dostop:
			self.cond.release()
			return
		
		val = self.items.pop()
		self.cond.release()
		
		return val

# Parent class for all internal representations of PA objects
class MP_object(object):
	keys = []
	
	def __init__(self, obj, get_attr):
		self._obj = obj
		self.get_attr = get_attr
	
	# store object attributes locally (required after the remote PA object vanished)
	def cache_obj(self):
		for k in self.keys:
			setattr(self, k.lower(), getattr(self, k))
	
	def __getattr__(self, attr):
		# check if requested attribute is part of a sub-object
		if attr.find(".") > -1:
			a = attr.split(".")
			obj = self
			for i in range(0, len(a)):
				if hasattr(obj, a[i]):
					obj = getattr(obj, a[i])
				else:
					raise AttributeError("%r object has no attribute %r" % (type(self).__name__, attr))
			return obj;
			raise AttributeError("%r object has no attribute %r" % (type(self).__name__, attr))
		
		# query PA over dbus if it knows the attribute
		val = self.get_attr(self._obj, attr)
		if val != None:
			return val
		
		raise AttributeError("%r object has no attribute %r" % (type(self).__name__, attr))
	
	# __str__ helper
	def getrepr(self):
		lst = {}
		
		for k in self.keys:
			if hasattr(self, k):
				lst[k] = getattr(self, k)
			elif hasattr(self, k.lower()):
				lst[k.lower()] = getattr(self, k.lower())
		
		return lst
	
	def __str__(self):
		return pformat(self.getrepr(), indent=5)