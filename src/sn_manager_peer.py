#!/usr/bin/python2
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import re
import socket
import logging
import time
from datetime import datetime
from gi.repository import GLib
from gi.repository import GObject

from sn_conn_peer import SnPeerServer
from sn_conn_peer import SnPeerClient
from sn_conn_peer import SnPeerHandShaker
from sn_conn_peer import SnPeerSocket
from sn_manager_config import SnVersion
from sn_manager_config import SnCfgSerializationObject
from sn_manager_local import SnSysInfo
from sn_manager_local import SnSysInfoUser
from sn_manager_local import SnSysInfoModule
from sn_manager_local import SnDataPacket

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
Peer FSM trigger table:

  STATE_NONE is the initial state.

  STATE_NONE      -> STATE_INIT      : socket connected
  STATE_INIT      -> STATE_VER_MATCH : object SnVersion recevied
  STATE_VER_MATCH -> STATE_CFG_MATCH : object SnCfgSerializationObject recevied
  STATE_CFG_MATCH -> STATE_FULL      : object SnSysInfo recevied

  STATE_INIT      -> STATE_REJECT    : reject sent, reject received
  STATE_VER_MATCH -> STATE_REJECT    : reject sent, reject received
  STATE_CFG_MATCH -> STATE_REJECT    : reject sent, reject received
  STATE_FULL      -> STATE_REJECT    : reject sent, reject received

  STATE_INIT      -> STATE_NONE      : socket error occured
  STATE_VER_MATCH -> STATE_NONE      : socket error occured
  STATE_CFG_MATCH -> STATE_NONE      : socket error occured
  STATE_FULL      -> STATE_NONE      : socket error occured
"""

"""
Peer FSM callback table:

  STATE_CFG_MATCH -> STATE_FULL      : call onPeerChange
  STATE_FULL                         : call onPeerChange when SnSysInfo is received
  STATE_FULL      -> STATE_REJECT    : call onPeerRemove
  STATE_FULL      -> STATE_NONE      : call onPeerRemove
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

class SnSysPacket:
	data = None						# object

class SnSysPacketReject:
	message = None					# str

class SnSysPacketKeepalive:
	pass

class SnPeerManager:

	POWER_OP_POWERON = 0
	POWER_OP_POWEROFF = 1
	POWER_OP_RESTART = 2
	POWER_OP_SUSPEND = 3
	POWER_OP_HIBERNATE = 4
	POWER_OP_HYBRID_SLEEP = 5

	POWER_STATE_UNKNOWN = 0
	POWER_STATE_RUNNING = 1
	POWER_STATE_POWEROFF = 2
	POWER_STATE_RESTARTING = 3
	POWER_STATE_SUSPEND = 4
	POWER_STATE_HIBERNATE = 5
	POWER_STATE_HYBRID_SLEEP = 6

	def __init__(self, param):
		logging.debug("SnPeerManager.__init__: Start")

		self.param = param

		# create internal peer info dict
		self.peerInfoDict = dict()
		for hn in self.param.configManager.getHostNameList():
			if hn == socket.gethostname():
				continue
			self.peerInfoDict[hn] = _PeerInfoInternal()
			self.peerInfoDict[hn].fsmState = _PeerInfoInternal.STATE_NONE
			self.peerInfoDict[hn].powerState = self.POWER_STATE_UNKNOWN

		# create handshaker
		self.handshaker = SnPeerHandShaker(self.param.certFile, self.param.privkeyFile, self.param.caCertFile, self.onSocketConnected)

		# create server endpoint
		self.serverEndPoint = SnPeerServer(self.handshaker)
		self.serverEndPoint.start(self.param.configManager.getHostInfo("localhost").port)

		# create client endpoint
		self.clientEndPoint = SnPeerClient(self.handshaker)

		# create timers
		self.peerProbeTimer = GObject.timeout_add_seconds(self.param.configManager.getPeerProbeInterval(), self.onPeerProbe)
		self.peerKeepaliveTimer = GObject.timeout_add_seconds(self.param.configManager.getPeerKeepaliveInterval(), self.onPeerKeepalive)

		logging.debug("SnPeerManager.__init__: End")
		return

	def dispose(self):
		logging.debug("SnPeerManager.dispose: Start")

		GLib.source_remove(self.peerKeepaliveTimer)
		GLib.source_remove(self.peerProbeTimer)

		self.clientEndPoint.dispose()
		self.serverEndPoint.dispose()
		self.handshaker.dispose()

		for peerName in self.peerInfoDict:
			self._shutdownPeer(peerName)

		logging.debug("SnPeerManager.dispose: End")
		return

	def getPeerNameList(self):
		return self.peerInfoDict.keys()

	def getPeerInfo(self, peerName):
		return self.peerInfoDict[peerName].infoObj

	def getPeerPowerState(self, peerName):
		return self.peerInfoDict[peerName].powerState

	def peerPowerOperation(self, peerName, opName):
		if opName == self.POWER_OP_POWERON:
			pass
		elif opName == self.POWER_OP_POWEROFF:
			pass
		elif opName == self.POWER_OP_RESTART:
			pass
		elif opName == self.POWER_OP_SUSPEND:
			pass
		elif opName == self.POWER_OP_HIBERNATE:
			pass
		elif opName == self.POWER_OP_HYBRID_SLEEP:
			pass
		else:
			assert False

	##### event callback ####

	def onSocketConnected(self, sslSock):
		logging.debug("SnPeerManager.onSocketConnected: Start")

		sock = SnPeerSocket(sslSock)

		# only peer in self-net is allowed
		if sock.getPeerName() not in self.peerInfoDict:
			sock.close()
			logging.debug("SnPeerManager.onSocketConnected: Fail, error1")
			return

		# only one connection between a pair of hosts
		if self.peerInfoDict[sock.getPeerName()].fsmState != _PeerInfoInternal.STATE_NONE:
			sock.close()
			logging.debug("SnPeerManager.onSocketConnected: Fail, error2")
			return

		# establish peerSocket
		sock.setEventFunc("recv", self.onSocketRecv)
		sock.setEventFunc("error", self.onSocketError)
		sock.setEventFunc("gracefulCloseComplete", self._gcComplete)

		# record sock
		self.peerInfoDict[sock.getPeerName()].fsmState = _PeerInfoInternal.STATE_INIT
		self.peerInfoDict[sock.getPeerName()].infoObj = None
		self.peerInfoDict[sock.getPeerName()].sock = sock

		# send localInfo
		self._sendObject(sock.getPeerName(), self.param.configManager.getVersion())
		self._sendObject(sock.getPeerName(), self.param.configManager.getCfgSerializationObject())
		self._sendObject(sock.getPeerName(), self.param.localManager.getLocalInfo())

		logging.debug("SnPeerManager.onSocketConnected: End")
		return

	def onSocketRecv(self, sock, packetObj):
		logging.debug("SnPeerManager.onSocketRecv: Start, %s", sock.getPeerName())
		
		peerName = sock.getPeerName()
		if self._typeCheck(packetObj, SnSysPacket):
			if self._typeCheck(packetObj.data, SnSysPacketKeepalive):
				logging.debug("SnPeerManager.onSocketRecv: _recvKeepalive, %s", datetime.now())
				self._recvKeepalive(peerName)
			elif self._typeCheck(packetObj.data, SnVersion):
				logging.debug("SnPeerManager.onSocketRecv: _recvVerMatch, %s", packetObj.data.version)
				self._recvVerMatch(peerName, packetObj.data)
			elif self._typeCheck(packetObj.data, SnCfgSerializationObject):
				logging.debug("SnPeerManager.onSocketRecv: _recvCfgMatch")
				self._recvCfgMatch(peerName, packetObj.data)
			elif self._typeCheck(packetObj.data, SnSysInfo):
				logging.debug("SnPeerManager.onSocketRecv: _recvPeerInfo")
				self._recvPeerInfo(peerName, packetObj.data)
			elif self._typeCheck(packetObj.data, SnSysPacketReject):
				logging.debug("SnPeerManager.onSocketRecv: _recvReject")
				self._recvReject(peerName, packetObj.data.message)
			else:
				self._sendReject(peerName, "invalid system packet data format")
		elif self._typeCheck(packetObj, SnDataPacket):
			self.param.localManager.onPacketRecv(peerName, packetObj.srcUserName, 
						packetObj.srcModuleName, packetObj.data)
		else:
			self._sendReject(peerName, "invalid packet format, %s"%(packetObj.__class__))

		logging.debug("SnPeerManager.onSocketRecv: End")
		return

	def onSocketError(self, sock):
		logging.debug("SnPeerManager.onSocketError: Start, %s", sock.getPeerName())
		self._shutdownPeer(sock.getPeerName())
		logging.debug("SnPeerManager.onSocketError: End")
		return

	def onPeerProbe(self):
		connectId = time.time()
		logging.debug("SnPeerManager.onPeerProbe: Start, %s, %d", datetime.now(), connectId)

		for pname, pinfo in self.peerInfoDict.items():
			if pinfo.fsmState == _PeerInfoInternal.STATE_NONE:
				self.clientEndPoint.connect(connectId, pname, self.param.configManager.getHostInfo(pname).port)

		logging.debug("SnPeerManager.onPeerProbe: End")
		return True

	def onPeerKeepalive(self):
		logging.debug("SnPeerManager.onPeerKeepalive: Start, %s", datetime.now())

		for pname, pinfo in self.peerInfoDict.items():
			if pinfo.fsmState not in [_PeerInfoInternal.STATE_NONE, _PeerInfoInternal.STATE_REJECT]:
				packetObj = SnSysPacket()
				packetObj.data = SnSysPacketKeepalive()
				pinfo.sock.send(packetObj)

		logging.debug("SnPeerManager.onPeerKeepalive: End")
		return True

	##### implementation ####

	def _recvKeepalive(self, peerName):
		# check state
		if self.peerInfoDict[peerName].fsmState != _PeerInfoInternal.STATE_FULL:
			self._sendReject(peerName, "keep-alive packet received in state other than state-full")
			return

	def _recvVerMatch(self, peerName, peerVersion):
		# check state
		if self.peerInfoDict[peerName].fsmState != _PeerInfoInternal.STATE_INIT:
			self._sendReject(peerName, "ver-match packet received in state other than state-init")
			return

		# check matching
		if peerVersion != self.param.configManager.getVersion():
			self._sendReject(peerName, "peer version not match")
			return

		# do operation
		self.peerInfoDict[peerName].fsmState = _PeerInfoInternal.STATE_VER_MATCH

	def _recvCfgMatch(self, peerName, peerCfgSerializationObject):
		# check state
		if self.peerInfoDict[peerName].fsmState != _PeerInfoInternal.STATE_VER_MATCH:
			self._sendReject(peerName, "cfg-match packet received in state other than state-ver-match")
			return

		# check matching
		if peerCfgSerializationObject != self.param.configManager.getCfgSerializationObject():
			self._sendReject(peerName, "peer configuration not match")
			return

		# do operation
		self.peerInfoDict[peerName].fsmState = _PeerInfoInternal.STATE_CFG_MATCH

	def _recvPeerInfo(self, peerName, peerInfo):
		# check state
		if self.peerInfoDict[peerName].fsmState != _PeerInfoInternal.STATE_CFG_MATCH:
			self._sendReject(peerName, "peer-info packet received in state other than state-cfg-match")
			return

		# check peer info
		if len(peerInfo.userList) != len(set(peerInfo.userList)):
			self._sendReject(peerName, "duplicate element in peer user list")
			return

		if len(peerInfo.moduleList) != len(set(peerInfo.moduleList)):
			self._sendReject(peerName, "duplicate element in peer module list")
			return

		for m in peerInfo.moduleList:
			strList = m.moduleName.split("-")
			if len(strList) < 3:
				self._sendReject(peerName, "invalid module name \"%s\""%(m.moduleName))
				return

			moduleScope = strList[0]
			if moduleScope not in ["sys", "usr"]:
				self._sendReject(peerName, "invalid module scope for module name \"%s\""%(m.moduleName))
				return

			moduleType = strList[1]
			if moduleType not in ["server", "client", "peer"]:
				self._sendReject(peerName, "invalid module type for module name \"%s\""%(m.moduleName))
				return

			moduleId = "-".join(strList[2:])
			if len(moduleId) > 32:
				self._sendReject(peerName, "module id is too long for module name \"%s\""%(m.moduleName))
				return
			if re.match("[A-Za-z0-9_]+", moduleId) is None:
				self._sendReject(peerName, "invalid module id for module name \"%s\""%(m.moduleName))
				return

		# do operation
		self.peerInfoDict[peerName].fsmState = _PeerInfoInternal.STATE_FULL
		self.peerInfoDict[peerName].infoObj = peerInfo

		# do notify
		self.param.localManager.onPeerChange(peerName)

	def _recvReject(self, peerName, rejectMessage):
		# record to log
		logging.warning("receive reject, %s, %s", peerName, rejectMessage)

		# do notify
		if self.peerInfoDict[peerName].fsmState == _PeerInfoInternal.STATE_FULL:
			self.param.localManager.onPeerRemove(peerName)

		# remove peer
		self.peerInfoDict[peerName].sock.close()
		self.peerInfoDict[peerName].fsmState = _PeerInfoInternal.STATE_REJECT
		self.peerInfoDict[peerName].infoObj = None
		self.peerInfoDict[peerName].sock = None

	def _sendObject(self, peerName, obj):
		packetObj = SnSysPacket()
		packetObj.data = obj
		self.peerInfoDict[peerName].sock.send(packetObj)

	def _sendReject(self, peerName, rejectMessage):
		# record to log
		logging.warning("send reject, closing gracefully, %s, %s", peerName, rejectMessage)

		# send reject message
		packetObj = SnSysPacket()
		packetObj.data = SnSysPacketReject()
		packetObj.data.message = rejectMessage
		self.peerInfoDict[peerName].sock.send(packetObj)

		# graceful close, wait reject message to be sent
		self.peerInfoDict[peerName].sock.gracefulClose()

	def _gcComplete(self, sock):
		peerName = sock.getPeerName()
		logging.warning("graceful close complete, %s", peerName)

		# do notify
		if self.peerInfoDict[peerName].fsmState == _PeerInfoInternal.STATE_FULL:
			self.param.localManager.onPeerRemove(peerName)

		# remove peer
		self.peerInfoDict[peerName].sock.close()
		self.peerInfoDict[peerName].fsmState = _PeerInfoInternal.STATE_REJECT
		self.peerInfoDict[peerName].infoObj = None
		self.peerInfoDict[peerName].sock = None

	def _sendDataObject(self, peerName, srcUserName, srcModuleName, obj):
		packetObj = SnDataPacket()
		packetObj.srcUserName = srcUserName
		packetObj.srcModuleName = srcModuleName
		packetObj.data = obj
		self.peerInfoDict[peerName].sock.send(packetObj)

	def _shutdownPeer(self, peerName):
		# record to log
		logging.warning("shutdown peer, %s", peerName)

		# do notify
		if self.peerInfoDict[peerName].fsmState == _PeerInfoInternal.STATE_FULL:
			self.param.localManager.onPeerRemove(peerName)

		# remove peer
		if self.peerInfoDict[peerName].sock is not None:		# _shutdownPeer can be called by dispose(), so add this check
			self.peerInfoDict[peerName].sock.close()
		self.peerInfoDict[peerName].fsmState = _PeerInfoInternal.STATE_NONE
		self.peerInfoDict[peerName].infoObj = None
		self.peerInfoDict[peerName].sock = None

	def _typeCheck(self, obj, typeobj):
		return str(obj.__class__) == str(typeobj)

class _PeerInfoInternal:
	STATE_NONE = 0
	STATE_INIT = 1
	STATE_VER_MATCH = 2
	STATE_CFG_MATCH = 3
	STATE_FULL = 4
	STATE_REJECT = 5

	fsmState = None				# enum
	powerState = None			# enum
	infoObj = None				# obj, SnSysInfo
	sock = None					# obj, peer socket

