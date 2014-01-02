#!/usr/bin/python2
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

from gi.repository import GObject
from sn_util import ServerEndPoint
from sn_util import ClientEndPoint
from sn_peer import SnPeer

class SnPeerInfo:

	STATE_INIT = 0
	STATE_INFO_SENT = 1
	STATE_INFO_SYNC = 2

	def __init__(self):
		self.state = STATE_INIT

class SnPeerManager(GObject.GObject):

	def __init__(self, param):
		GObject.GObject.__init__(self)
		self.param = param

		# define variables
		self.localInfo = None
		self.peerDict = dict()		# _SnPeer object contains peerInfo

		self.serverEndPoint = None
		self.clientEndPoint = None

		# fill info dict
		self.localInfo = SnPeerInfo()
		for hn in self.param.configManager.getHostList():
			if hn == socket.gethostname():
				continue
			self.peerDict[hn] = _SnPeer()

		# create server endpoint
		self.serverEndPoint = ServerEndPoint(self.param.certFile, self.param.privkeyFile,
		                                     self.param.caCertFile, self._onSocketConnceted)
		self.serverEndPoint.listen(self.param.configManager.getHostInfo("localhost").port)

		# create client endpoint
		self.clientEndPoint = ClientEndPoint(self.param.certFile, self.param.privkeyFile,
		                                     self.param.caCertFile, self._onSocketConnceted)

		# create peer probe timer
		GObject.timeout_add_seconds(self.param.configManager.getCfgGlobal().peerProbeTimeout * 1000,
		                            self._onPeerProbe)

	def release(self):
		# fixme
		pass

	def getPeerNameList(self):
		return self.peerDict.keys()

	def getPeerInfo(self, peerName):
		return self.peerDict[peerName].peerInfo

	def _onSocketConnceted(self, sock):
		peerName = sock.getPeerName()

		# only accept host belongs to myself
		if peerName not in self.peerDict:
			sock.close()
			return

		# only one connection between a pair of hosts
		if self.peerDict[peerName].peerSocket is not None:
			sock.close()
			return

		self.peerDict[peerName]._onSocketNew(sock)

	def _onPeerProbe(self):
		for po in self.peerDict.values():
			if po.peerSocket is not None:
				continue

			self.clientEndPoint.connect(po.peerName, self.param.configManager.getHostInfo(po.peerName).port)

class _SnPeer:

	STATE_NONE = 0
	STATE_INFO_SENT = 1
	STATE_INFO_SYNC = 2

	CHANNEL_INFO = 1

	def __init__(self, peerManager):
		self.m = peerManager
		self.peerInfo = None

		self.peerSocket = None
		self.state = STATE_NONE

	def _onSocketNew(self, sock):
		assert self.peerSocket is None

		self.peerSocket = sock
		self.peerSocket.setFunc(


		self.peerSocket.send(CHANNEL_INFO, pickle.dumps(self.m.localInfo))
		self.state = STATE_INFO_SENT

	def _onSocketRecv(self, channel, buf):
		assert self.peerSocket is not None

		if self.state == STATE_INFO_SENT and channel == CHANNEL_INFO:
			ro = pickle.loads(buf)
			if not isinstance(ro, SnPeerInfo):
				self._shutdown()
				return
			else:
				self.peerInfo = ro
				self.state = STATE_INFO_SYNC

	def _onSocketClose(self):
		assert self.peerSocket is not None

		self.state = STATE_NONE

	def _onSocketError(self):
		assert self.peerSocket is not None

		self.state = STATE_NONE


	def _shutdown(self):
		self.peerSocket.close()
		self.peerSocket = None
		self.state = STATE_NONE

