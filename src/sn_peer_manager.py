#!/usr/bin/python2
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

from gi.repository import GObject
from sn_util import ServerEndPoint
from sn_util import ClientEndPoint
from sn_peer import SnPeer

class SnPeerInfo:
	systemServerList = None			# list<SnPeerInfoServer>
	systemClientList = None			# list<SnPeerInfoClient>
	userInfoDict = None				# dict<str, SnPeerInfoUser>

class SnPeerInfoUser:
	userId = None					# int
	userServerList = None			# list<SnPeerInfoServer>
	userClientList = None			# list<SnPeerInfoClient>

class SnPeerInfoServer:
	serviceName = None				# str

class SnPeerInfoClient:
	serviceName = None				# str
	toSystem = None					# boolean

class SnPeerManager(GObject.GObject):

	def __init__(self, param):
		GObject.GObject.__init__(self)
		self.param = param

		# define variables
		self.localInfo = None
		self.peerDict = dict()		# _SnPeer object contains peerInfo

		self.serverEndPoint = None
		self.clientEndPoint = None

		# fill info variables
		self.localInfo = self.param.serviceManager.getLocalInfo()
		for hn in self.param.configManager.getHostList():
			if hn == socket.gethostname():
				continue
			self.peerDict[hn] = _SnPeer(hn)

		# create server endpoint
		self.serverEndPoint = ServerEndPoint(self.param.certFile, self.param.privkeyFile, self.param.caCertFile)
		self.serverEndPoint.setAllowedPeerList(self.peerDict.keys())
		self.serverEndPoint.setEventFunc("accept", self._onSocketConnceted)
		self.serverEndPoint.listen(self.param.configManager.getHostInfo("localhost").port)

		# create client endpoint
		self.clientEndPoint = ClientEndPoint(self.param.certFile, self.param.privkeyFile, self.param.caCertFile)
		self.clientEndPoint.setEventFunc("connect", self._onSocketConnceted)

		# create peer probe timer
		GObject.timeout_add_seconds(self.param.configManager.getCfgGlobal().peerProbeTimeout * 1000, self._onPeerProbe)

	def release(self):
		# fixme
		pass

	def getPeerNameList(self):
		return self.peerDict.keys()

	def isPeerActive(self, peerName):
		return (self.peerDict[peerName].peerInfo is not None)

	def getPeerInfo(self, peerName):
		return self.peerDict[peerName].peerInfo

	def _onSocketConnceted(self, sock):
		# only one connection between a pair of hosts
		if self.peerDict[sock.getPeerName()].peerSocket is not None:
			sock.close()
			return

		self.peerDict[sock.getPeerName()]._onSocketNew(sock)

	def _onPeerProbe(self):
		for po in self.peerDict.values():
			if po.peerSocket is None:
				self.clientEndPoint.connect(po.peerName, self.param.configManager.getHostInfo(po.peerName).port)

class _SnPeer:

	STATE_NONE = 0
	STATE_INFO_SENT = 1
	STATE_INFO_SYNC = 2

	CHANNEL_INFO = 0

	def __init__(self, peerManager, peerName):
		self.m = peerManager
		self.peerName = peerName
		self.peerInfo = None

		self.peerSocket = None
		self.state = STATE_NONE

	def _onSocketNew(self, sock):
		assert self.peerSocket is None

		self.peerSocket = sock
		self.peerSocket.setFunc("recv", self._onSocketRecv)
		self.peerSocket.setFunc("error", self._onSocketError)

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

	def _onSocketError(self):
		assert self.peerSocket is not None
		self._shutdown()

	def _shutdown(self):
		self.peerSocket.close()
		self.peerSocket = None
		self.state = STATE_NONE

