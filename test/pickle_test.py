#!/usr/bin/python2
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import sys
import pickle
import jsonpickle
import json

class A:
	def __init__(self):
		self.a1 = 10
		self.a2 = "abcd"
		self.b3 = B()

class B:
	def __init__(self):
		self.b1 = 20
		self.b2 = True
		self.b3 = -5

a = A()

#print json.dumps(a)
#print jsonpickle.encode(a)

str = pickle.dumps(a)

obj = pickle.loads(str)
print isinstance(obj, A)
