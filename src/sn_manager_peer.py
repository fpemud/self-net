#!/usr/bin/python2
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import socket
from datetime import datetime
from gi.repository import GObject

import flogging
from sn_conn_peer import SnPeerServer
from sn_conn_peer import SnPeerClient
from sn_manager_config import SnVersion
from sn_manager_config import SnCfgSerializationObject

"""
Peer FSM specification:

  STATE_NONE:
      peer.infoObj : None
      peer.sock    : None

  STATE_INIT:
      peer.infoObj : None
      peer.sock    : not None

  STATE_VER_MATCH:
      peer.infoObj : None
      peer.sock    : not None

  STATE_CFG_MATCH:
      peer.infoObj : None
      peer.sock    : not None

  STATE_FULL:
      peer.infoObj : not None
      peer.sock    : not None

  STATE_REJECT:
      peer.infoObj : None
      peer.sock    : None
"""

"""
Peer FSM graph:

  STATE_NONE      -> STATE_INIT      : socket connected
  STATE_INIT      -> STATE_VER_MATCH : object SnVersion recevied
  STATE_VER_MATCH -> STATE_CFG_MATCH : object SnCfgSerializationObject recevied
  STATE_CFG_MATCH -> STATE_FULL      : object SnPeerInfo recevied

  STATE_INIT      -> STATE_REJECT    : protocol error occured
  STATE_VER_MATCH -> STATE_REJECT    : protocol error occured
  STATE_CFG_MATCH -> STATE_REJECT    : protocol error occured
  STATE_FULL      -> STATE_REJECT    : protocol error occured

  STATE_INIT      -> STATE_NONE      : socket error occured
  STATE_VER_MATCH -> STATE_NONE      : socket error occured
  STATE_CFG_MATCH -> STATE_NONE      : socket error occured
  STATE_FULL      -> STATE_NONE      : socket error occured
"""

"""
Peer FSM notes:
  Peers can do data communication in STATE_FULL.
  After a peer enters STATE_REJECT, we won't connect to it, but we still accept
its connection. According to the protocol, both end will enter STATE_REJECT, so
only when one end restarts the connection can be back on again. There's only one
exception: one end enters STATE_REJECT, the other end enters STATE_NONE. Then
the conenction will be reestablished by the STATE_NONE end.
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
			self.peerInfoDict[hn].state = _PeerInfoInternal.STATE_INIT

		# create server endpoint
		self.serverEndPoint = SnPeerServer(self.param.certFile, self.param.privkeyFile, self.param.caCertFile)
		self.serverEndPoint.setEventFunc("accept", self._onSocketConnected)
		self.serverEndPoint.start(self.param.configManager.getHostInfo("localhost").port)

		# create client endpoint
		self.clientEndPoint = SnPeerClient(self.param.certFile, self.param.privkeyFile, self.param.caCertFile)
		self.clientEndPoint.setEventFunc("connected", self._onSocketConnected)

		# create timers
		self.peerProbeTimer = GObject.timeout_add_seconds(self.param.configManager.getPeerProbeInterval() * 1000, self._onPeerProbe)
		self.peerKeepaliveTimer = GObject.timeout_add_seconds(self.param.configManager.getPeerKeepaliveInterval() * 1000, self._onPeerKeepalive)

	def getPeerNameList(self):
		return self.peerInfoDict.keys()

	def getPeerInfo(self, peerName):
		return self.peerInfoDict[peerName].infoObj

	##### event callback ####

	def _onSocketConnected(self, sock):
		flogging.functionStart(sock.getPeerName())

		# only peer in self-net is allowed
		if sock.getPeerName() not in self.peerInfoDict:
			sock.close()
			flogging.functionFail("err1")
			return

		# only one connection between a pair of hosts
		if self.peerInfoDict[sock.getPeerName()].state != _PeerInfoInternal.STATE_NONE:
			sock.close()
			flogging.functionFail("err2")
			return

		# establish peerSocket
		sock.setEventFunc("recv", self._onSocketRecv)
		sock.setEventFunc("error", self._onSocketError)

		# send localInfo
		sock.send(self.param.configManager.getVersion())
		sock.send(self.param.configManager.getCfgSerializationObject())
		sock.send(self.param.serviceManager.getLocalInfo())

		# record sock
		self.peerInfoDict[sock.getPeerName()].state = _PeerInfoInternal.STATE_INIT
		self.peerInfoDict[sock.getPeerName()].infoObj = None
		self.peerInfoDict[sock.getPeerName()].sock = sock

		flogging.functionSucc()

	def _onSocketRecv(self, sock, packetObj):
		flogging.functionStart(sock.getPeerName())

		peerName = sock.getPeerName()
		if isinstance(packetObj, SnSysPacket):
			if isinstance(packetObj.data, SnSysPacketKeepalive):
				flogging.debug("_recvKeepalive, %s", datetime.now())
				self._recvKeepalive(peerName)
			elif isinstance(packetObj.data, SnVersion):
				flogging.debug("_recvVerMatch", packetObj.data.version)
				self._recvVerMatch(peerName, packetObj.data)
			elif isinstance(packetObj.data, SnCfgSerializationObject):
				flogging.debug("_recvCfgMatch")
				self._recvCfgMatch(peerName, packetObj.data)
			elif isinstance(packetObj.data, SnPeerInfo):
				flogging.debug("_recvPeerInfo")
				self._recvPeerInfo(peerName, packetObj.data)
			elif isinstance(packetObj.data, SnSysPacketReject):
				flogging.debug("_recvReject")
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

		flogging.functionEnd()

	def _onSocketError(self, sock):
		flogging.functionStart(sock.getPeerName())
		self._shutdownPeer(sock.getPeerName())
		flogging.functionEnd()

	def _onPeerProbe(self):
		flogging.functionStart(datetime.now())

		for pname, pinfo in self.peerInfoDict.values():
			if pinfo.state == _PeerInfoInternal.STATE_NONE:
				self.clientEndPoint.connect(pname, self.param.configManager.getHostInfo(pname).port)

		flogging.functionEnd()
		return True

	def _onPeerKeepalive(self):
		flogging.functionStart(datetime.now())

		for pname, pinfo in self.peerInfoDict.values():
			if pinfo.state not in [_PeerInfoInternal.STATE_NONE, _PeerInfoInternal.STATE_REJECT]:
				packetObj = SnSysPacket()
				packetObj.data = SnSysPacketKeepalive()
				pinfo.sock.send(packetObj)

		flogging.functionEnd()
		return True

	##### implementation ####

	def _recvKeepalive(self, peerName):
		# check state
		if self.peerInfoDict[peerName].state != _PeerInfoInternal.STATE_FULL:
			self._rejectPeer(peerName, "keep-alive packet received in state other than state-full")
			return

	def _recvVerMatch(self, peerName, peerVersion):
		# check state
		if self.peerInfoDict[peerName].state != _PeerInfoInternal.STATE_INIT:
			self._rejectPeer(peerName, "ver-match packet received in state other than state-init")
			return

		# check matching
		if peerVersion != self.param.configManager.getVersion():
			self._rejectPeer(peerName, "peer version not match")
			return

		# do operation
		self.peerInfoDict[peerName].state = _PeerInfoInternal.STATE_VER_MATCH

	def _recvCfgMatch(self, peerName, peerCfgSerializationObject):
		# check state
		if self.peerInfoDict[peerName].state != _PeerInfoInternal.STATE_VER_MATCH:
			self._rejectPeer(peerName, "cfg-match packet received in state other than state-ver-match")
			return

		# check matching
		if peerCfgSerializationObject != self.param.configManager.getCfgSerializationObject():
			self._rejectPeer(peerName, "peer configuration not match")
			return

		# do operation
		self.peerInfoDict[peerName].state = _PeerInfoInternal.STATE_CFG_MATCH

	def _recvPeerInfo(self, peerName, peerInfo):
		# check state
		if self.peerInfoDict[peerName].state != _PeerInfoInternal.STATE_CFG_MATCH:
			self._rejectPeer(peerName, "peer-info packet received in state other than state-cfg-match")
			return

		# check peer info
		if len(peerInfo.userList) != len(set(peerInfo.userList)):
			self._rejectPeer(peerName, "duplicate element in peer user list")
			return
		if len(peerInfo.moduleList) != len(set(peerInfo.moduleList)):
			self._rejectPeer(peerName, "duplicate element in peer module list")
			return

		# do operation
		self.peerInfoDict[peerName].state = _PeerInfoInternal.STATE_FULL
		self.peerInfoDict[peerName].infoObj = peerInfo

		# do notify
		self.param.localManager.onPeerChange(peerName)

	def _recvReject(self, peerName, rejectMessage):
		# record to log
		flogging.warning("receive reject from peer, %s, %s", peerName, rejectMessage)

		# do notify
		self.param.localManager.onPeerRemove(peerName)

		# remove peer
		self.peerInfoDict[peerName].sock.close()
		self.peerInfoDict[peerName].state = _PeerInfoInternal.STATE_REJECT
		self.peerInfoDict[peerName].infoObj = None
		self.peerInfoDict[peerName].sock = None

	def _rejectPeer(self, peerName, rejectMessage):
		# record to log
		flogging.warning("send reject to peer, %s, %s", peerName, rejectMessage)

		# send reject message
		packetObj = SnSysPacket()
		packetObj.data = SnDataPacketReject()
		packetObj.data.message = rejectMessage
		self.peerInfoDict[peerName].sock.send(packetObj)

		# do notify
		self.param.localManager.onPeerRemove(peerName)

		# remove peer
		self.peerInfoDict[peerName].sock.gracefulClose()
		self.peerInfoDict[peerName].state = _PeerInfoInternal.STATE_REJECT
		self.peerInfoDict[peerName].infoObj = None
		self.peerInfoDict[peerName].sock = None

	def _shutdownPeer(self, peerName):
		# record to log
		flogging.warning("shutdown peer, %s", peerName)

		# do notify
		self.param.localManager.onPeerRemove(peerName)

		# remove peer
		self.peerInfoDict[peerName].sock.close()
		self.peerInfoDict[peerName].state = _PeerInfoInternal.STATE_NONE
		self.peerInfoDict[peerName].infoObj = None
		self.peerInfoDict[peerName].sock = None

class _PeerInfoInternal:
	STATE_NONE = 0
	STATE_INIT = 1
	STATE_VER_MATCH = 2
	STATE_CFG_MATCH = 3
	STATE_FULL = 4
	STATE_REJECT = 5

	state = None				# enum
	infoObj = None				# obj, SnPeerInfo
	sock = None					# obj, peer socket

