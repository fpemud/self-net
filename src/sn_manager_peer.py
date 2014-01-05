#!/usr/bin/python2
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

from gi.repository import GObject
from sn_util import ServerEndPoint
from sn_util import ClientEndPoint

class SnPeerInfo:
	systemAgentList = None			# list<SnPeerInfoAgent>
	systemClientList = None			# list<SnPeerInfoClient>
	userInfoList = None				# list<SnPeerInfoUser>

class SnPeerInfoUser:
	userId = None					# int
	userName = None					# str
	userAgentList = None			# list<SnPeerInfoAgent>
	userClientList = None			# list<SnPeerInfoClient>

class SnPeerInfoAgent:
	serviceName = None				# str
	label = None					# int

class SnPeerInfoClient:
	serviceName = None				# str

class SnPeerManager(GObject.GObject):

	def __init__(self, param):
		GObject.GObject.__init__(self)
		self.param = param

		# create local info
		self.localInfo = self.param.serviceManager.getLocalInfo()

		# create peer info
		self.peerInfoDict = dict()
		self.peerSockDict = dict()
		for hn in self.param.configManager.getHostList():
			if hn == socket.gethostname():
				continue
			self.peerInfoDict[hn] = None
			self.peerSockDict[hn] = None

		# create server endpoint
		self.serverEndPoint = ServerEndPoint(self.param.certFile, self.param.privkeyFile, self.param.caCertFile)
		self.serverEndPoint.setEventFunc("accept", self._onSocketConnected)
		self.serverEndPoint.listen(self.param.configManager.getHostInfo("localhost").port)

		# create client endpoint
		self.clientEndPoint = ClientEndPoint(self.param.certFile, self.param.privkeyFile, self.param.caCertFile)
		self.clientEndPoint.setEventFunc("connect", self._onSocketConnected)

		# create peer probe timer
		GObject.timeout_add_seconds(self.param.configManager.getCfgGlobal().peerProbeTimeout * 1000, self._onPeerProbe)

	def release(self):
		# fixme
		pass

	def getPeerNameList(self):
		return self.peerInfoDict.keys()

	def isPeerActive(self, peerName):
		return (self.peerSockDict[peerName] is not None)

	def getPeerInfo(self, peerName):
		return self.peerInfoDict[peerName]

	def dataToPeer(self, peerName, serviceKey, data):
		pass		

	def _onSocketConnected(self, sock):
		# only peer in self-net is allowed
		if sock.getPeerName not in self.peerInfoDict:
			sock.close()
			return

		# only one connection between a pair of hosts
		if self.peerSockDict[sock.getPeerName()] is not None:
			sock.close()
			return

		# establish peerSocket
		sock.setFunc("label_recv", 0, self._onSocketLabelRecvInfo)
		sock.setFunc("recv", self._onSocketRecv, True)
		sock.setFunc("error", self._onSocketError)

		# send localInfo
		sock.send(0, pickle.dumps(self.localInfo))

		# record sock
		self.peerSockDict[sock.getPeerName()] = sock

	def _onSocketLabelRecvInfo(self, sock, label, data):
		# receive, check and record remote peer info, shutdown peer on error
		peerInfo = None
		try:
			peerInfo = pickle.loads(data)
			self._checkPeerInfo(peerInfo)
		except _PeerInfoCheckException:
			self._shutdownPeer(sock.getPeerName())
			return

		self.peerInfoDict[sock.getPeerName()] = peerInfo

	def _onSocketRecv(self, sock, label, packet):
		self.param.localManager.dataToApp(label, packet)

	def _onSocketError(self, sock):
		self._shutdownPeer(sock.getPeerName())

	def _onPeerProbe(self):
		for pname, psock in self.peerSockDict.values():
			if psock is None:
				self.clientEndPoint.connect(pname, self.param.configManager.getHostInfo(pname).port)

	def _shutdownPeer(self, peerName):
		self.peerInfoDict[peerName] = None
		self.peerSockDict[peerName].close()
		self.peerSockDict[peerName] = None

	def _checkPeerInfo(self, peerInfo):
		if not isinstance(peerInfo, SnPeerInfo):
			raise _PeerInfoCheckException("invalid class of peer info object")

		labelList = []
		for i in peerInfo.systemAgentList:
			if i.label in labelList:
				raise _PeerInfoCheckException("label repeat in peer info")
			labelList.append(i.label)
		for i in peerInfo.systemClientList:
			if i.label in labelList:
				raise _PeerInfoCheckException("label repeat in peer info")
			labelList.append(i.label)
		for u in peerInfo.userList:
			for i in u.userAgentList:
				if i.label in labelList:
					raise _PeerInfoCheckException("label repeat in peer info")
				labelList.append(i.label)
			for i in u.userClientList:
				if i.label in labelList:
					raise _PeerInfoCheckException("label repeat in peer info")
				labelList.append(i.label)

class _PeerInfoCheckException(Exception):
	def __init__(self, msg):
		super(_PeerInfoException, self).__init__(self, msg)

