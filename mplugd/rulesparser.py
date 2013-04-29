#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Author: Mario Kicherer (http://kicherer.org)
# License: GPL v2 (http://www.gnu.org/licenses/gpl-2.0.txt)
#
# This is a custom INI-like configuration parser similar to ConfigParser
# but besides "=" it also accepts "!=" and "*=" to match regular expressions,
# as well as multiple values per key.
#

import re

# extend str to store the separator
class MyRulesValue(str):
	def __new__(cls,sep,value):
		obj = str.__new__(cls, value)
		obj.sep = sep
		return obj

class MyRulesParser(object):
	seps = ["!=", "*=", "="]
	
	def __init__(self):
		self._dict = {}
	
	# parse filename
	def read(self, filename):
		f = open(filename, "r")
		lines = f.readlines()
		
		if len(lines) == 0:
			return
		
		section = self._dict
		idx = 0
		while idx < len(lines):
			stripped = lines[idx].strip()
			
			# ignore comments
			if stripped=="" or stripped[0] == ";" or stripped[0] == "#":
				idx +=1
				continue
			
			# new section?
			if stripped[0] == "[":
				secname = stripped[1:stripped.find("]")]
				if secname in self._dict:
					print "Warning: double section", secname
				else:
					self._dict[secname] = {}
				section = self._dict[secname]
				idx +=1
				continue
			
			# split line in three parts: key, separator, value
			for sep in self.seps:
				part = lines[idx].partition(sep)
				if part[1] == sep:
					break
			if part[1] != sep:
				print "no separator found in line", idx, "\"%s\"" % (lines[idx])
				return
			
			# either create new value list or add to existing list
			if not part[0] in section:
				section[part[0]] = [MyRulesValue(part[1], part[2][:-1])]
			else:
				section[part[0]].append(MyRulesValue(part[1], part[2][:-1]))
			
			idx += 1
		
		f.close()
	
	def sections(self):
		return [k for k,v in self._dict.items() if type(v) == dict]
	
	def items(self, section):
		return [(k,v) for k,v in self._dict[section].items()]
	
	def has_option(self, section, key):
		return key in self._dict[section]
	
	def has_section(self, section):
		return (section in self._dict) and (type(self._dict[section]) == dict)
	
	def get(self, section, key):
		return self._dict[section][key]
	
	# test if "test" matches one of the values
	def match(self, values, test):
		for v in values:
			#expression = "\"%s\"" % v + seper + "\"%s\"" %test
			#return eval(expression)
			
			if v.sep == "=" and str(v) == str(test):
				return True
			if v.sep == "!=" and str(v) != str(test):
				return True
			if v.sep == "*=" and re.search(str(v), str(test)) != None:
				return True
		return False

if __name__ == '__main__':
	parser = MyRulesParser()
	parser.read("action.d/02-test.rules")
	
	import pprint
	pprint.pprint(parser._dict)
	
	print parser.sections()