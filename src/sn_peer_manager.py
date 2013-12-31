#!/usr/bin/python2
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import socket
from gi.repository import GObject
from gi.repository import GLib
from sn_util import ServerEndPoint
from sn_util import ClientEndPoint
from sn_peer import SnPeer

class SnPeerManager(GObject.GObject):

	__gsignals__ = {
		'peer_add': (GObject.SIGNAL_RUN_LAST, GObject.TYPE_NONE, ()),
		'peer_delete': (GObject.SIGNAL_RUN_LAST, GObject.TYPE_NONE, ()),
	}

	def __init__(self, param):
		GObject.GObject.__init__(self)
		self.param = param
		self.peerList = []
		self.servSocket = None
		self.coreSocketDict = dict()

	def init(self):
		self.param.configManager.connect("host_add", self._onCfgPeerAdd)
		self.param.configManager.connect("host_delete", self._onCfgPeerDelete)
		self.param.configManager.connect("host_delete", self._onCfgPeerDelete)

		# create server socket
		self.servSocket = ServerEndPoint(self.param.certFile, self.param.privkeyFile,
		                                 self.param.caCertFile, None, None, None)
		self.servSocket.listen(self.param.)

		
		self._createServerSocket()

		# create peer probe timer
		GObject.timeout_add_seconds(self.param.peerProbeTimeout, self._peerProbeTimerProc)

	def getPeerList(self):
		"""Returns SnPeer object list"""

		return self.peerList

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

	def _onCfgPeerAdd(self, peerObj):
		po = SnPeer(self.param, peerObj.hostname)
		self.peerList.append(po)

	def _onCfgPeerDelete(self, peerName):
		for p in self.peerList:
			if p.getName() == peerName:
				print "peer deleted"
				self.peerList.remove(p)
				return
		assert False

	def _onPeerProbeTimeout(self):
		print "_peerProbeTimerProc"
		return True

	def _onServerSocketEvent(self, source, cb_condition):
		assert source == self.servSocket

		if cb_condition & GLib.IO_IN:
			ss, addr = source.accept()
			if self._getPeerByAddr() == addr[0]:
				ss.close()

	def _connectToPeer(self, peerObj):
		assert peerObj.peerSocket is None

		s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		try:
			s.connect(peerObj.getName())
		except:
			s.close()
			return

		GLib.io_add_watch(self.servSocket, GLib.IO_IN | GLib.IO_PRI | GLib.IO_ERR | GLib.IO_HUP, self._onServerSocketEvent)

	def _getPeerByAddr(self, addr):
		for item in self.peerList:
			if item.peerSocket is None:
				continue
			if item.peerSocket.getpeername()[0] == addr:
				return item
		return None

GObject.type_register(SnPeerManager)

