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

class SnSysPacketPowerOp:
	name = None						# str

class SnSysPacketPowerOpError:
	message = None					# str

class SnSysPacketPowerState:
	name = None						# str

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
		self.peerProbeTimer = None
		self.peerKeepaliveTimer = None
		self._timerOperation()

		logging.debug("SnPeerManager.__init__: End")
		return

	def dispose(self):
		logging.debug("SnPeerManager.dispose: Start")

		if self.peerKeepaliveTimer is not None:
			ret = GLib.source_remove(self.peerKeepaliveTimer)
			assert ret
		if self.peerProbeTimer is not None:
			ret = GLib.source_remove(self.peerProbeTimer)
			assert ret

		self.clientEndPoint.dispose()
		self.serverEndPoint.dispose()
		self.handshaker.dispose()

		for peerName, peerInfo in self.peerInfoDict.items():
			if (peerInfo.fsmState == _PeerInfoInternal.STATE_INIT
					or peerInfo.fsmState == _PeerInfoInternal.STATE_VER_MATCH
					or peerInfo.fsmState == _PeerInfoInternal.STATE_CFG_MATCH
					or peerInfo.fsmState == _PeerInfoInternal.STATE_FULL):
				self._shutdownPeer(peerName, _PeerInfoInternal.STATE_NONE)

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
		sock = SnPeerSocket(sslSock)
		peerName = sock.getPeerName()

		# only peer in self-net is allowed
		if peerName not in self.peerInfoDict:
			sock.close()
			logging.debug("SnPeerManager.onSocketConnected: Fail, error1")
			return

		# only one connection between a pair of hosts
		if self.peerInfoDict[peerName].fsmState != _PeerInfoInternal.STATE_NONE:
			sock.close()
			logging.debug("SnPeerManager.onSocketConnected: Fail, error2")
			return

		# establish peerSocket
		sock.setEventFunc("recv", self.onSocketRecv)
		sock.setEventFunc("error", self.onSocketError)
		sock.setEventFunc("gracefulCloseComplete", self._gcComplete)

		# record sock
		oldFsmState = self.peerInfoDict[peerName].fsmState
		self.peerInfoDict[peerName].fsmState = _PeerInfoInternal.STATE_INIT
		self.peerInfoDict[peerName].infoObj = None
		self.peerInfoDict[peerName].sock = sock
		logging.debug("SnPeerManager.onSocketConnected: %s", _dbgmsg_peer_state_change(peerName, oldFsmState, self.peerInfoDict[peerName].fsmState))

		# timer operation
		self._timerOperation()

		# send localInfo
		self._sendObject(peerName, self.param.configManager.getVersion())
		self._sendObject(peerName, self.param.configManager.getCfgSerializationObject())
		self._sendObject(peerName, self.param.localManager.getLocalInfo())

	def onSocketRecv(self, sock, packetObj):
		peerName = sock.getPeerName()
		if self._typeCheck(packetObj, SnSysPacket):
			if self._typeCheck(packetObj.data, SnSysPacketKeepalive):
				self._recvKeepalive(peerName)
			elif self._typeCheck(packetObj.data, SnVersion):
				self._recvVerMatch(peerName, packetObj.data)
			elif self._typeCheck(packetObj.data, SnCfgSerializationObject):
				self._recvCfgMatch(peerName, packetObj.data)
			elif self._typeCheck(packetObj.data, SnSysInfo):
				self._recvPeerInfo(peerName, packetObj.data)
			elif self._typeCheck(packetObj.data, SnSysPacketPowerOp):
				logging.debug("SnPeerManager.onSocketRecv: _recvPowerOp")
				self._recvPowerOp(peerName, packetObj.data)
			elif self._typeCheck(packetObj.data, SnSysPacketPowerOpError):
				logging.debug("SnPeerManager.onSocketRecv: _recvPowerOpError")
				self._recvPowerOpError(peerName, packetObj.data)
			elif self._typeCheck(packetObj.data, SnSysPacketPowerState):
				logging.debug("SnPeerManager.onSocketRecv: _recvPowerState")
				self._recvPowerState(peerName, packetObj.data)
			elif self._typeCheck(packetObj.data, SnSysPacketReject):
				self._recvReject(peerName, packetObj.data.message)
			else:
				self._sendReject(peerName, "invalid system packet data format")
		elif self._typeCheck(packetObj, SnDataPacket):
			self.param.localManager.onPacketRecv(peerName, packetObj.srcUserName, 
						packetObj.srcModuleName, packetObj.data)
		else:
			self._sendReject(peerName, "invalid packet format, %s"%(packetObj.__class__))

	def onSocketError(self, sock):
		peerName = sock.getPeerName()
		oldFsmState = self._shutdownPeer(peerName, _PeerInfoInternal.STATE_NONE)
		logging.debug("SnPeerManager.onSocketError: %s", _dbgmsg_peer_state_change(peerName, oldFsmState, _PeerInfoInternal.STATE_NONE))
		self._timerOperation()

	def onPeerProbe(self):
		connectId = time.time()
		for pname, pinfo in self.peerInfoDict.items():
			if pinfo.fsmState == _PeerInfoInternal.STATE_NONE:
				self.clientEndPoint.connect(connectId, pname, self.param.configManager.getHostInfo(pname).port)
		return True

	def onPeerKeepalive(self):
		for pname, pinfo in self.peerInfoDict.items():
			if pinfo.fsmState not in [_PeerInfoInternal.STATE_NONE, _PeerInfoInternal.STATE_REJECT]:
				packetObj = SnSysPacket()
				packetObj.data = SnSysPacketKeepalive()
				pinfo.sock.send(packetObj)
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
		oldFsmState = self.peerInfoDict[peerName].fsmState
		self.peerInfoDict[peerName].fsmState = _PeerInfoInternal.STATE_VER_MATCH
		logging.debug("SnPeerManager._recvVerMatch: %s", _dbgmsg_peer_state_change(peerName, oldFsmState, self.peerInfoDict[peerName].fsmState))

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
		oldFsmState = self.peerInfoDict[peerName].fsmState
		self.peerInfoDict[peerName].fsmState = _PeerInfoInternal.STATE_CFG_MATCH
		logging.debug("SnPeerManager._recvCfgMatch: %s", _dbgmsg_peer_state_change(peerName, oldFsmState, self.peerInfoDict[peerName].fsmState))

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
		oldFsmState = self.peerInfoDict[peerName].fsmState
		self.peerInfoDict[peerName].fsmState = _PeerInfoInternal.STATE_FULL
		self.peerInfoDict[peerName].infoObj = peerInfo
		logging.debug("SnPeerManager._recvPeerInfo: %s", _dbgmsg_peer_state_change(peerName, oldFsmState, self.peerInfoDict[peerName].fsmState))

		# do notify
		self.param.localManager.onPeerChange(peerName)

	def _recvPowerOp(self, peerName, powerOp):
		if powerOp.name == "poweroff":
			assert False
		elif powerOp.name == "restart":
			assert False
		elif powerOp.name == "suspend":
			assert False
		elif powerOp.name == "hibernate":
			assert False
		elif powerOp.name == "hybrid-sleep":
			assert False
		else:
			self._sendReject(peerName, "invalid power operation name \"%s\""%(powerOp.name))

	def _recvPowerOpError(self, peerName, powerOpError):
		pass

	def _recvPowerState(self, peerName, powerState):
		if powerState.name == "poweroff":
			assert False
		elif powerState.name == "restarting":
			assert False
		elif powerState.name == "suspend":
			assert False
		elif powerState.name == "hibernate":
			assert False
		elif powerState.name == "hybrid-sleep":
			assert False
		else:
			self._sendReject(peerName, "invalid power state name \"%s\""%(powerState.name))

	def _recvReject(self, peerName, rejectMessage):
		logging.warning("receive reject, %s, %s", peerName, rejectMessage)

		# do notify
		if self.peerInfoDict[peerName].fsmState == _PeerInfoInternal.STATE_FULL:
			self.param.localManager.onPeerRemove(peerName)

		# remove peer
		oldFsmState = self.peerInfoDict[peerName].fsmState
		self.peerInfoDict[peerName].sock.close()
		self.peerInfoDict[peerName].fsmState = _PeerInfoInternal.STATE_REJECT
		self.peerInfoDict[peerName].infoObj = None
		self.peerInfoDict[peerName].sock = None
		logging.debug("SnPeerManager._recvReject: %s", _dbgmsg_peer_state_change(peerName, oldFsmState, self.peerInfoDict[peerName].fsmState))

	def _sendObject(self, peerName, obj):
		packetObj = SnSysPacket()
		packetObj.data = obj
		self.peerInfoDict[peerName].sock.send(packetObj)

	def _sendReject(self, peerName, rejectMessage):
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
		oldFsmState = self._shutdownPeer(peerName, _PeerInfoInternal.STATE_REJECT)
		logging.debug("SnPeerManager._gcComplete: %s", _dbgmsg_peer_state_change(peerName, oldFsmState, _PeerInfoInternal.STATE_REJECT))
		self._timerOperation()

	def _sendDataObject(self, peerName, srcUserName, srcModuleName, obj):
		packetObj = SnDataPacket()
		packetObj.srcUserName = srcUserName
		packetObj.srcModuleName = srcModuleName
		packetObj.data = obj
		self.peerInfoDict[peerName].sock.send(packetObj)

	def _shutdownPeer(self, peerName, dstState):
		assert dstState in [ _PeerInfoInternal.STATE_NONE, _PeerInfoInternal.STATE_REJECT ]

		# do notify
		if self.peerInfoDict[peerName].fsmState == _PeerInfoInternal.STATE_FULL:
			self.param.localManager.onPeerRemove(peerName)

		# remove peer
		oldFsmState = self.peerInfoDict[peerName].fsmState
		self.peerInfoDict[peerName].sock.close()
		self.peerInfoDict[peerName].fsmState = dstState
		self.peerInfoDict[peerName].infoObj = None
		self.peerInfoDict[peerName].sock = None

		return oldFsmState

	def _timerOperation(self):
		hasNotNone = any(x for x in self.peerInfoDict.values() if x.sock is not None)
		hasNone = any(x for x in self.peerInfoDict.values() if x.sock is None)

		if not hasNone:
			if self.peerProbeTimer is not None:
				logging.debug("SnPeerManager._timerOperation: PeerProbeTimer stops")
				GLib.source_remove(self.peerProbeTimer)
				self.peerProbeTimer = None
		if not hasNotNone:
			if self.peerKeepaliveTimer is not None:
				logging.debug("SnPeerManager._timerOperation: PeerKeepaliveTimer stops")
				GLib.source_remove(self.peerKeepaliveTimer)
				self.peerKeepaliveTimer = None
		if hasNone:
			if self.peerProbeTimer is None:
				logging.debug("SnPeerManager._timerOperation: PeerProbeTimer starts")
				interval = self.param.configManager.getPeerProbeInterval()
				self.peerProbeTimer = GObject.timeout_add_seconds(interval, self.onPeerProbe)
		if hasNotNone:
			if self.peerKeepaliveTimer is None:
				logging.debug("SnPeerManager._timerOperation: PeerKeepaliveTimer starts")
				interval = self.param.configManager.getPeerKeepaliveInterval()
				self.peerKeepaliveTimer = GObject.timeout_add_seconds(interval, self.onPeerKeepalive)

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

def _dbgmsg_peer_state_change(peerName, oldPeerState, peerState):
	return "Peer %s, %s -> %s"%(peerName, _peer_state_to_str(oldPeerState), _peer_state_to_str(peerState))

def _peer_state_to_str(peerState):
	if peerState == _PeerInfoInternal.STATE_NONE:
		return "STATE_NONE"
	elif peerState == _PeerInfoInternal.STATE_INIT:
		return "STATE_INIT"
	elif peerState == _PeerInfoInternal.STATE_VER_MATCH:
		return "STATE_VER_MATCH"
	elif peerState == _PeerInfoInternal.STATE_CFG_MATCH:
		return "STATE_CFG_MATCH"
	elif peerState == _PeerInfoInternal.STATE_FULL:
		return "STATE_FULL"
	elif peerState == _PeerInfoInternal.STATE_REJECT:
		return "STATE_REJECT"
	else:
		assert False

