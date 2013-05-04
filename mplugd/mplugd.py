#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Author: Mario Kicherer (http://kicherer.org)
# License: GPL v2 (http://www.gnu.org/licenses/gpl-2.0.txt)
#
# This is the main file for mplugd
#

import os, argparse, sys, subprocess

from header import *
from rulesparser import *


# thread that pops events from queue and processes them
class Event_Consumer(threading.Thread):
	def __init__(self, queue):
		self.queue = queue
		#self.stop = False
		threading.Thread.__init__(self)
		
	def run(self):
		while not self.queue.dostop:
			# pop blocks
			val = self.queue.pop()
			if val:
				if val.ignore:
					if mplugd.verbose:
						print "Ignoring event: ", val
					continue
				
				if mplugd.verbose:
					print "Handling event: ", val
				self.handle_event(val)
	
	def handle_event(self, e):
		mplugd.laststate = get_state();
		
		for directory in mplugd.config["action_directory"]:
			directory = os.path.expanduser(directory)
			sys.path.append(directory)
			for root, dirs, files in os.walk(directory):
				files.sort()
				for filename in files:
					fullpath = os.path.join(root, filename)
					
					if filename.split(".")[-1] == "py":
						mod = __import__(".".join(filename.split(".")[:-1]))
						mod.process(mplugd, e)
					
					if filename.split(".")[-1] == "rules":
						execute_rules(fullpath, e)

# substitute %variables% in value
def rules_substitute_value(event, value):
	import re
	
	result = ""
	res = True
	while res:
		res = re.search("%([\w\._\s]*)%", value)
		if res:
			# replace %% with %
			if res.group(1) == "":
				result = result + value[:res.start()] + "%"
				value = value[res.end():]
				continue
			
			sub = ""
			vlist = res.group(1).split("_")
			
			if vlist[0] == "event" and event.item and hasattr(event.item, "_".join(vlist[1:])):
				sub = getattr(event.item, "_".join(vlist[1:]))
			if vlist[0] in mplugd.laststate and vlist[1] in mplugd.laststate[vlist[0]] and hasattr(mplugd.laststate[vlist[0]][vlist[1]], "_".join(vlist[2:])):
				sub = getattr(mplugd.laststate[vlist[0]][vlist[1]], "_".join(vlist[2:]))
			
			# result contains the substituted part of value
			result = result + value[:res.start()] + str(sub)
			# value contains the unprocessed part of the original value
			value = value[res.end():]
	
	# return substituted string and the remaining part of value
	return result + value

# process rules file from action.d/
def execute_rules(filename, event):
	if mplugd.verbose:
		print "Executing rules", filename
	
	sparser = MyRulesParser()
	sparser.read(filename)
	
	for s in sparser.sections():
		typ = s.split(" ")
		if not typ[0] == "rule":
			continue
		
		if mplugd.verbose:
			print "Processing section", s
		
		# evaluate all if conditions in this section
		execute = True
		for (k,values) in sparser.items(s):
			# we're only interested in conditions here
			if k.split("_")[0] == "true" or k.split("_")[0] == "false":
				continue
			
			if mplugd.verbose:
				print "Item: %s %s %s ..." %(k, values[0].sep, values),
			
			if k[:len("if_present_")] == "if_present_":
				# if_present_output_name=DP-0
				ki = k[len("if_present_"):].split("_")
				
				found = False
				if not ki[0] in mplugd.laststate:
					continue
				for (idx, obj) in mplugd.laststate[ki[0]].items():
					if sparser.match(values, getattr(obj,"_".join(ki[1:]))):
						found = True
						break;
				if found:
					if mplugd.verbose:
						print "found"
				else:
					if mplugd.verbose:
						print "not found"
					execute = False
					break
			
			elif k[:len("if_")] == "if_":
				# if_output_DP-0_connected=1
				
				ki = k[len("if_"):].split("_")
				
				if not ki[0] in mplugd.laststate:
					if mplugd.verbose:
						print ki[0], "not found"
					execute = False
					break
				
				# get output id for output name
				outputid = None
				for k2,v2 in mplugd.laststate[ki[0]].items():
					if v2.name == ki[1]:
						outputid = k2
						break
				
				if outputid:
					if not sparser.match(values, str(getattr(mplugd.laststate[ki[0]][outputid], "_".join(ki[2:])))):
						execute = False
						if mplugd.verbose:
							print "mismatch: =\"%s\"" % (getattr(mplugd.laststate[ki[0]][outputid], "_".join(ki[2:])))
						break
					else:
						if mplugd.verbose:
							print "match"
				else:
					if mplugd.verbose:
						print ki[1], "not found"
					execute = False
					break
			
			elif k.startswith("on_type"):
				# on_type=NewPlaybackStream
				
				if not event:
					print "no event"
					execute = False
					break
				
				if not sparser.match(values, event.etype):
					if mplugd.verbose:
						print "mismatch", event.etype
					execute = False
					break
				else:
					if mplugd.verbose:
						print "match"
			
			elif k.startswith("on_"):
				# on_name*=DP-[0-9]
				
				if not event:
					print "no event"
					execute = False
					break
				
				found=False
				pl = k.split("_")
				for p in plugins:
					if pl[1] in p.keywords:
						found = True
						break
				
				if found:
					if not p.handle_rule_cmd(sparser, pl, values, mplugd.laststate, event):
						print "no match"
						execute = False
						break
				else:
					pl = k[3:]
					
					if not hasattr(event.item, pl) or not sparser.match(values, getattr(event.item, pl)):
						if mplugd.verbose:
							print "mismatch ",
							if hasattr(event.item, pl):
								print getattr(event.item, pl)
							else:
								print "no such attr"
						execute = False
						break
						
					if mplugd.verbose:
						print "match"
			
			else:
				if mplugd.verbose:
					print "skipped"
		
		# find true/false statements and pass them to the respective plugin
		for k,v in sparser.items(s):
			pl = k.split("_")
			
			if not pl[0] == str(execute).lower():
				continue
			
			for p in plugins:
				if pl[1] in p.keywords:
					p.handle_rule_cmd(sparser, pl, v, mplugd.laststate, event)
					break
		
		# we execute true/false commands directly
		cmd = None
		if execute:
			if sparser.has_option(s, "true_exec"):
				cmd = sparser.get(s, "true_exec")
		else:
			if sparser.has_option(s, "false_exec"):
				cmd = sparser.get(s, "false_exec")
		if cmd:
			for c in cmd:
				c = rules_substitute_value(event, c)
				if mplugd.verbose:
					print "exec", c
				subprocess.call(c, shell=True)

# query plugins for their state
def get_state():
	state = {}
	
	for plugin in plugins:
		plugin.get_state(state)
	
	return state

# stop all threads
def shutdown():
	q.stop()
	c.join()
	
	for plugin in plugins:
		if mplugd.verbose:
			print "Stopping...", plugin.__name__
		plugin.shutdown()
	
	for plugin in plugins:
		plugin.join()
		
	c.join()

################################
### main

def main():
	global plugins
	global q
	global c
	global mplugd
	
	parser = argparse.ArgumentParser(description='Executes user-defined actions on XRANDR events')
	parser.add_argument('-v', dest='verbose', help='verbose output', action='store_true')
	parser.add_argument('-d', dest='state_dump', help='only dump state', action='store_true')

	args = parser.parse_args()

	# set configuration
	mplugd = MPlugD()
	mplugd.verbose = args.verbose
	state_dump = args.state_dump

	q = EventQueue()

	# start thread that pops events from queue and processes them
	c = Event_Consumer(q)
	c.start()

	# initialize plugins
	plugins = []
	sys.path.append(os.path.dirname(__file__))
	for directory in mplugd.config["plugin_directory"]:
		directory = os.path.expanduser(directory)
		sys.path.append(directory)
		for root, dirs, files in os.walk(directory):
			files.sort()
			for filename in files:
				fullpath = os.path.join(root, filename)
				
				if filename[:2] == "pi" and filename.split(".")[-1] == "py":
					if mplugd.verbose:
						print "starting plugin", filename
					mod = __import__(".".join(filename.split(".")[:-1]))
					
					# initialize all constructs
					if not mod.initialize(mplugd, q):
						print "Initialization of plugin %s failed" % filename
						continue
					plugins.append(mod)
					
					# start event loop thread
					mod.eventloop.start()

	# wait until all plugins are initialized
	for plugin in plugins:
		plugin.eventloop.initflag.wait()

	# store current state so we still have some information about an item
	# after it vanished
	mplugd.laststate = get_state();

	# print all we know about the current state and exit
	if state_dump:
		print "Xorg:"
		print ""
		for k,v in mplugd.laststate["output"].items():
			print v.name, k, "------"
			print str(v)
		
		print ""
		print "PulseAudio:"
		print ""
		for k,v in mplugd.laststate["sink"].items():
			print k, "------"
			print str(v)
		
		print ""
		for k,v in mplugd.laststate["stream"].items():
			print k, "------"
			print str(v)
		
		shutdown()
		sys.exit(0)

	if mplugd.verbose:
		print "Processing static rules..."
	# process rules that do not depend on an event
	q.push(MP_Event("Startup"))

	# loop until we're intercepted
	import time
	while 1:
		try:
			time.sleep(1)
		except KeyboardInterrupt:
			q.push(MP_Event("Shutdown"))
			shutdown()
			break

if __name__ == "__main__":
	main()
