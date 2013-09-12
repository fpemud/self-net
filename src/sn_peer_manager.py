#!/usr/bin/python2
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import socket  
from gi.repository import GObject
from gi.repository import GLib

class SnPeerManager(GObject.GObject):

	def __init__(self, param):
		GObject.GObject.__init__(self)
		self.param = param
		self.peerList = []
		self.servSocket = None
		self.coreSocketDict = dict()

	def init(self):
		# create peer list
		for p in self.param.configManager.getCfgPeerList():
			po = SnPeer(self.param, p.hostname)
			self.peerList.append(po)
		self.param.configManager.connect("cfg_peer_added", self._onCfgPeerAdded)
		self.param.configManager.connect("cfg_peer_deleted", self._onCfgPeerDeleted)

		# create server socket
		self._createServerSocket()

		# create peer probe timer
		GObject.timeout_add_seconds(self.param.peerProbeTimeout, self._peerProbeTimerProc)

	def getPeerList(self):
		"""Returns peer name list"""

		return self.param.configManager.getPeerList()

	def getPeer(self, peerName):
		"""Returns SnPeer object"""

		for pobj in self.peerList:
			if pobj.getName() == peerName:
				return pobj
		assert False

	def _createServerSocket(self):
		address = ('0.0.0.0', self.param.configManager.getPort())
		self.servSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		self.servSocket.bind(address)  
		self.servSocket.listen(5)  
		GLib.io_add_watch(self.servSocket, GLib.IO_IN | GLib.IO_PRI | GLib.IO_ERR | GLib.IO_HUP, self._onServerSocketEvent)

	def _peerProbeTimerProc(self):
		print "_peerProbeTimerProc"
		return True

	def _onServerSocketEvent(self, source, cb_condition):
		assert source == self.servSocket

		if cb_condition & GLib.IO_IN:
			ss, addr = source.accept()  

	def _onCfgPeerAdded(self):
		pass

	def _onCfgPeerDeleted(self):
		pass

GObject.type_register(SnPeerManager)




