#!/usr/bin/python2
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import socket
from gi.repository import GObject
from sn_conn_peer import SnPeerServer
from sn_conn_peer import SnPeerClient

"""
Some specification:
1. after we reject a peer or be rejected by a peer, we won't connect to it, but we still accept its connection.
2. peer enters active state when we get its peer info
3. 
"""

class SnPeerInfo:
	userList = None					# list<SnPeerInfoUser>
	moduleList = None				# list<SnPeerInfoModule>

class SnPeerInfoUser:
	userName = None					# str

	def __eq__(self, other):
		return isinstance(other, self.__class__) and self.userName == other.userName
	def __ne__(self, other):
		return not self.__eq__(other)
	def __hash__(self):
		return hash(self.userName)

class SnPeerInfoModule:
	moduleName = None				# str
	userName = None					# str

	def __eq__(self, other):
		return isinstance(other, self.__class__) and self.moduleName == other.moduleName and self.userName == other.userName
	def __ne__(self, other):
		return not self.__eq__(other)
	def __hash__(self):
		return hash(self.moduleName) ^ hash(self.userName)

class SnSysPacket:
	data = None						# object

class SnSysPacketReject:
	message = None					# str

class SnSysPacketKeepalive:
	pass

class SnDataPacket:
	srcUserName = None				# str, can be None
	srcModuleName = None			# str
	data = None						# object

class SnDataPacketReject:
	message = None					# str

class SnPeerManager:

	def __init__(self, param):
		self.param = param

		# create internal peer info dict
		self.peerInfoDict = dict()
		for hn in self.param.configManager.getHostNameList():
			if hn == socket.gethostname():
				continue
			self.peerInfoDict[hn] = _PeerInfoInternal()
			self.peerInfoDict[hn].rejected = False

		# create server endpoint
		self.serverEndPoint = SnPeerServer(self.param.certFile, self.param.privkeyFile, self.param.caCertFile)
		self.serverEndPoint.setEventFunc("accept", self._onSocketConnected)
		self.serverEndPoint.start(self.param.configManager.getHostInfo("localhost").port)

		# create client endpoint
		self.clientEndPoint = SnPeerClient(self.param.certFile, self.param.privkeyFile, self.param.caCertFile)
		self.clientEndPoint.setEventFunc("connected", self._onSocketConnected)

		# create peer probe timer
		GObject.timeout_add_seconds(self.param.configManager.getPeerProbeInterval() * 1000, self._onPeerProbe)
		GObject.timeout_add_seconds(self.param.configManager.getPeerKeepaliveInterval() * 1000, self._onPeerKeepalive)

	def getPeerNameList(self):
		return self.peerInfoDict.keys()

	def getPeerInfo(self, peerName):
		return self.peerInfoDict[peerName].infoObj

	##### event callback ####

	def _onSocketConnected(self, sock):
		# only peer in self-net is allowed
		if sock.getPeerName() not in self.peerInfoDict:
			sock.close()
			return

		# only one connection between a pair of hosts
		if self.peerInfoDict[sock.getPeerName()].sock is not None:
			sock.close()
			return

		# establish peerSocket
		sock.setEventFunc("recv", self._onSocketRecv)
		sock.setEventFunc("error", self._onSocketError)

		# send localInfo
		sock.send(self.param.serviceManager.getLocalInfo())

		# record sock
		self.peerInfoDict[sock.getPeerName()].infoObj = None
		self.peerInfoDict[sock.getPeerName()].sock = sock
		self.peerInfoDict[sock.getPeerName()].rejected = False

	def _onSocketRecv(self, sock, packetObj):
		peerName = sock.getPeerName()
		if isinstance(packetObj, SnSysPacket):
			if isinstance(packetObj.data, SnSysPacketKeepalive):
				self._recvKeepalive(peerName)
			elif isinstance(packetObj.data, SnPeerInfo):
				self._recvPeerInfo(peerName, packetObj.data)
			elif isinstance(packetObj.data, SnSysPacketReject):
				self._recvReject(peerName, packetObj.data.message)
			else:
				self._rejectPeer(peerName, "invalid system packet data format")
		elif isinstance(packetObj, SnDataPacket):
			if isinstance(packetObj.data, SnDataPacketReject):
				self.param.localManager.onReject(peerName, packetObj.srcUserName, 
						packetObj.srcModuleName, packetObj.data.message)
			else:
				self.param.localManager.onRecv(peerName, packetObj.srcUserName, 
						packetObj.srcModuleName, packetObj.data)
		else:
			self._rejectPeer(peerName, "invalid packet format")

	def _onSocketError(self, sock):
		self._shutdownPeer(sock.getPeerName())

	def _onPeerProbe(self):
		for pname, pinfo in self.peerInfoDict.values():
			if pinfo.sock is not None:
				continue
			if pinfo.rejected:
				continue
			self.clientEndPoint.connect(pname, self.param.configManager.getHostInfo(pname).port)
		return True

	def _onPeerKeepalive(self):
		for pname, pinfo in self.peerInfoDict.values():
			if pinfo.sock is None:
				continue
			packetObj = SnSysPacket()
			packetObj.data = SnSysPacketKeepalive()
			pinfo.sock.send(packetObj)
		return True

	##### implementation ####

	def _recvKeepalive(self, peerName):
		if self.peerInfoDict[peerName].infoObj is None:
			self._rejectPeer(peerName, "peer info needed")

	def _recvPeerInfo(self, peerName, peerInfo):
		# check peer info
		if len(peerInfo.userList) != len(set(peerInfo.userList)):
			self._rejectPeer(peerName, "duplicate element in peer user list")
			return
		if len(peerInfo.moduleList) != len(set(peerInfo.moduleList)):
			self._rejectPeer(peerName, "duplicate element in peer module list")
			return

		# record peer info
		self.peerInfoDict[peerName].infoObj = peerInfo
		self.param.localManager.onPeerChange(peerName)

	def _recvReject(self, peerName, rejectMessage):
		# record to log
		pass

		# remove peer
		self.param.localManager.onPeerRemove(peerName)
		self.peerInfoDict[peerName].sock.close()
		self.peerInfoDict[peerName].infoObj = None
		self.peerInfoDict[peerName].sock = None
		self.peerInfoDict[peerName].rejected = True

	def _rejectPeer(self, peerName, rejectMessage):
		# record to log
		pass

		# send reject message
		packetObj = SnSysPacket()
		packetObj.data = SnDataPacketReject()
		packetObj.data.message = rejectMessage
		self.peerInfoDict[peerName].sock.send(packetObj)

		# remove peer
		self.param.localManager.onPeerRemove(peerName)
		self.peerInfoDict[peerName].sock.close()
		self.peerInfoDict[peerName].infoObj = None
		self.peerInfoDict[peerName].sock = None
		self.peerInfoDict[peerName].rejected = True

	def _shutdownPeer(self, peerName):
		# record to log
		pass

		# remove peer
		self.param.localManager.onPeerRemove(peerName)
		self.peerInfoDict[peerName].sock.close()
		self.peerInfoDict[peerName].infoObj = None
		self.peerInfoDict[peerName].sock = None
		self.peerInfoDict[peerName].rejected = False

class _PeerInfoInternal:
	infoObj = None				# obj, SnPeerInfo
	sock = None					# obj, peer socket
	rejected = None				# bool

