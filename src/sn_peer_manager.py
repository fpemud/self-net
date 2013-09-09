#!/usr/bin/python2
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import socket  
from gi.repository import GObject

class SnPeerManagerParam:
	peerProbeTimeout = 0
	peerKeepAliveTimeout = 0

class SnPeerManager(GObject.GObject):

	def __init__(self, param, pmParam):
		GObject.GObject.__init__(self)
		self.param = param
		self.pmParam = pmParam
		self.peerList = []
		self.servSocket = None
		self.coreSocketDict = dict()

	def init(self):
		# create server socket
		self._createServerSocket()

		# create peer probe timer
		gobject.timeout_add_seconds(self.pmParam.peerProbeTimeout, self._peerProbeTimerProc)

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
		glib.io_add_watch(self.servSocket, glib.IO_IN | glib.IO_PRI | glib.IO_ERR | glib.IO_HUP, self._onServerSocketEvent)

	def _peerProbeTimerProc(self):
		print "_peerProbeTimerProc"
		return True

	def _onServerSocketEvent(self, source, cb_condition):
		assert source == self.servSocket

		if cb_condition & glib.IO_IN:
			ss, addr = source.accept()  

GObject.type_register(SnPeerManager)

class _PeerExchangeProto:

	def get




