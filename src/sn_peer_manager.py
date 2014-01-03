#!/usr/bin/python2
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

from gi.repository import GObject
from sn_util import ServerEndPoint
from sn_util import ClientEndPoint

class SnPeerInfo:
	systemServerList = None			# list<SnPeerInfoServer>
	systemClientList = None			# list<SnPeerInfoClient>
	userInfoList = None				# list<SnPeerInfoUser>

class SnPeerInfoUser:
	userId = None					# int
	userName = None					# str
	userServerList = None			# list<SnPeerInfoServer>
	userClientList = None			# list<SnPeerInfoClient>

class SnPeerInfoServer:
	serviceName = None				# str
	serviceLabel = None				# int

class SnPeerInfoClient:
	serviceName = None				# str
	serviceLabel = None				# int
	toSystem = None					# boolean

class SnPeerManager(GObject.GObject):

	def __init__(self, param):
		GObject.GObject.__init__(self)
		self.param = param

		# define variables
		self.peerDict = dict()		# _SnPeer object contains peerInfo

		self.serverEndPoint = None
		self.clientEndPoint = None

		# fill info
		for hn in self.param.configManager.getHostList():
			if hn == socket.gethostname():
				continue
			self.peerDict[hn] = _SnPeer(self.param, hn)

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

	def __init__(self, param, peerManager, peerName):
		self.param = param
		self.peerManager = peerManager
		self.peerName = peerName
		self.peerInfo = None
		self.peerSocket = None

	def _onSocketNew(self, sock):
		assert self.peerSocket is None

		# establish peerSocket
		self.peerSocket = sock
		self.peerSocket.setFunc("label_recv", 0, self._onSocketLabelRecvInfo)
		self.peerSocket.setFunc("recv", self._onSocketRecv)
		self.peerSocket.setFunc("error", self._onSocketError)

		# send localInfo
		self.peerSocket.send(0, pickle.dumps(self.param.serviceManager.getLocalInfo()))

	def _onSocketLabelRecvInfo(self, sock, label, data):
		ro = pickle.loads(data)
		if not isinstance(ro, SnPeerInfo):
			self._shutdown()
			return

		self.peerInfo = ro

	def _onSocketRecv(self, sock, label, data):
		pass

	def _onSocketError(self):
		self._shutdown()

	def _shutdown(self):
		self.peerSocket.close()
		self.peerSocket = None

