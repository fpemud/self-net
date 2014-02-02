#!/usr/bin/python2
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import socket
from gi.repository import GObject
from sn_conn_peer import SnPeerServer
from sn_conn_peer import SnPeerClient

class SnPeerInfo:
	moduleList = None				# list<SnPeerInfoModule>
	userList = None					# list<SnPeerInfoUser>

class SnPeerInfoUser:
	userName = None					# str

class SnPeerInfoModule:
	moduleName = None				# str
	userName = None					# str

class SnSysPacket:
	srcPeerName = None				# str
	data = None						# object

class SnDataPacket:
	srcPeerName = None				# str
	srcUserName = None				# str, can be None
	srcModuleName = None			# str
	data = None						# object

class SnDataPacketReject:
	message = None					# str

class SnPeerManager(GObject.GObject):

	def __init__(self, param):
		GObject.GObject.__init__(self)
		self.param = param

		# create peer info
		self.peerInfoDict = dict()
		self.peerSockDict = dict()
		for hn in self.param.configManager.getHostNameList():
			if hn == socket.gethostname():
				continue
			self.peerInfoDict[hn] = None
			self.peerSockDict[hn] = None

		# create server endpoint
		self.serverEndPoint = SnPeerServer(self.param.certFile, self.param.privkeyFile, self.param.caCertFile)
		self.serverEndPoint.setEventFunc("accept", self._onSocketConnected)
		self.serverEndPoint.start(self.param.configManager.getHostInfo("localhost").port)

		# create client endpoint
		self.clientEndPoint = SnPeerClient(self.param.certFile, self.param.privkeyFile, self.param.caCertFile)
		self.clientEndPoint.setEventFunc("connected", self._onSocketConnected)

		# create peer probe timer
		GObject.timeout_add_seconds(self.param.configManager.getCfgGlobal().peerProbeInterval * 1000, self._onPeerProbe)

	def getPeerNameList(self):
		return self.peerInfoDict.keys()

	def isPeerActive(self, peerName):
		return (self.peerSockDict[peerName] is not None)

	def getPeerInfo(self, peerName):
		return self.peerInfoDict[peerName]

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
		sock.send(0, pickle.dumps(self.param.serviceManager.getLocalInfo()))

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

	def _notifyPeerStateChange(self, peerName, notifyType):
		self.param.localManager.



class _PeerInfoCheckException(Exception):
	def __init__(self, msg):
		super(_PeerInfoException, self).__init__(self, msg)

