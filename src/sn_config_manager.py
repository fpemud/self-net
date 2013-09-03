#!/usr/bin/python2
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import pyinotify

class SnCfgPeer:
	hostname = ""
	publicKey = ""

class SnConfigManager:
	"""/etc/self-net
	    |----key
	          |----public-key.rsa			# mode 644
	          |----private-key.rsa			# mode 600
	    |----hosts
	          |----HOSTNAME1
	                |----public-key.rsa
	          |----HOSTNAME2
	                |----public-key.rsa"""

	def __init__(self, param):
		self.param = param

	def init(self):
		pass

	def getPublicKey(self):
		pass

	def getCfgPeerList(self):
		pass

	def getCfgPeer(self, peerName):
		pass


