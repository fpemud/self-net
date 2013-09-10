#!/usr/bin/python2
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import os
import pyinotify
from gi.repository import GObject

class SnCfgPeer:
	hostname = ""
	publicKey = ""

class SnConfigManager(GObject.GObject):
	"""/etc/self-net
	    |----key
	          |----rsa-key-public.pem			# mode 644
	          |----rsa-key-private.pem			# mode 600
	    |----peers
	          |----HOSTNAME1
	                |----rsa-key-public.pem
	          |----HOSTNAME2
	                |----rsa-key-public.pem"""

	__gsignals__ = {
		'cfg_peer_added': (GObject.SIGNAL_RUN_LAST, GObject.TYPE_NONE, ()),
		'cfg_peer_delete': (GObject.SIGNAL_RUN_LAST, GObject.TYPE_NONE, ()),
	}

	def __init__(self, param):
		self.param = param
		self.listenPort = 2107
		self.publicKey = ""
		self.cfgPeerList = []

	def init(self):
		# add all peers
		for f in sorted(os.listdir(self.param.cfgDir)):
			pobj = SnCfgPeer()
			pobj.hostname = f
			pobj.publicKey = ""

			self.cfgPeerList.append(pobj)
			self.emit("cfg_peer_added", pobj)

	def getPort(self):
		return self.listenPort

	def getPublicKey(self):
		return self.publicKey

	def getCfgPeerList(self):
		"""Returns peer name list"""

		ret = []
		for item in self.cfgPeerList:
			ret.append(item.hostname)
		return ret

	def getCfgPeer(self, peerName):
		"""Returns SnCfgPeer object"""

		for item in self.cfgPeerList:
			if item.hostname == peerName:
				return item
		assert False

GObject.type_register(SnConfigManager)

