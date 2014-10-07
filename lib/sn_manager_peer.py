#!/usr/bin/python3
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import re
import socket
import logging
import dbus
from datetime import datetime
from objsocket import objsocket
from gi.repository import GLib
from gi.repository import GObject

from sn_util import SnUtil
from sn_conn_peer import SnPeerServer
from sn_conn_peer import SnPeerClient
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
  STATE_FULL      -> STATE_REJECT    : call onPeerChange
  STATE_FULL      -> STATE_NONE      : call onPeerChange
"""

"""
Peer FSM state notes:
  Peers can do data communication in STATE_FULL.
  After a peer enters STATE_REJECT, we won't connect to it, but we still accept
its connection. According to the protocol, both end will enter STATE_REJECT, so
only when one end restarts the connection can be back on again. There's only one
exception: one end enters STATE_REJECT, the other end enters STATE_NONE. Then
the conenction will be reestablished by the STATE_NONE end.
"""

"""
Peer power state notes:
  Power state equals to POWER_STATE_RUNNING when peer is connected, equals to
POWER_STATE_UNKNOWN when it is in reject.
  Peer should send SnSysPacketPowerStateWhenInactive before it goes offline so we
can give it a proper power state when it's inactive. If it fails to do so, it's
power state should be POWER_STATE_UNKNOWN.
"""

class SnSysPacket:
	data = None						# object

class SnSysPacketReject:
	message = None					# str

class SnSysPacketPowerOp:
	name = None						# str

class SnSysPacketPowerOpAck:
	error_message = None			# str, None means success, not-None means failure

class SnSysPacketPowerStateWhenInactive:
	name = None						# str

class SnPeerManager:

	POWER_STATE_UNKNOWN = 0
	POWER_STATE_POWEROFF = 1
	POWER_STATE_REBOOTING = 2
	POWER_STATE_SUSPEND = 3
	POWER_STATE_HIBERNATE = 4
	POWER_STATE_HYBRID_SLEEP = 5
	POWER_STATE_RUNNING = 6

	def __init__(self, param):
		logging.debug("SnPeerManager.__init__: Start")

		self.param = param
		self.disposeCompleteFunc = None

		# create internal peer info dict
		self.peerInfoDict = dict()
		for hn in self.param.configManager.getHostNameList():
			if hn == socket.gethostname():
				continue
			self.peerInfoDict[hn] = _PeerInfoInternal()
			self.peerInfoDict[hn].fsmState = _PeerInfoInternal.STATE_NONE
			self.peerInfoDict[hn].powerStateWhenInactive = self.POWER_STATE_UNKNOWN

		# create server endpoint
		self.serverEndPoint = SnPeerServer(self.param.certFile, self.param.privkeyFile, self.param.caCertFile, self.onSocketConnected)
		self.serverEndPoint.start(self.param.configManager.getHostInfo("localhost").port)

		# create client endpoint
		self.clientEndPoint = SnPeerClient(self.param.certFile, self.param.privkeyFile, self.param.caCertFile, self.onSocketConnected)

		# create timers
		self.peerProbeTimer = None
		self._timerOperation()

		logging.debug("SnPeerManager.__init__: End")
		return

	def dispose(self, disposeCompleteFunc):
		logging.debug("SnPeerManager.dispose: Start")

		if self.peerProbeTimer is not None:
			ret = GLib.source_remove(self.peerProbeTimer)
			assert ret

		self.clientEndPoint.dispose()
		self.serverEndPoint.dispose()

		for peerName, peerInfo in self.peerInfoDict.items():
			if (peerInfo.fsmState == _PeerInfoInternal.STATE_INIT
					or peerInfo.fsmState == _PeerInfoInternal.STATE_VER_MATCH
					or peerInfo.fsmState == _PeerInfoInternal.STATE_CFG_MATCH
					or peerInfo.fsmState == _PeerInfoInternal.STATE_FULL):
				self._peerToShutdown(peerName)

		self.disposeCompleteFunc = disposeCompleteFunc
		SnUtil.idleInvoke(self._disposeComplete)

	def getPeerNameList(self):
		return list(self.peerInfoDict.keys())

	def getPeerInfo(self, peerName):
		return self.peerInfoDict[peerName].infoObj

	def getPeerPowerState(self, peerName):
		if self.peerInfoDict[peerName].fsmState == _PeerInfoInternal.STATE_NONE:
			return self.peerInfoDict[peerName].powerStateWhenInactive
		elif self.peerInfoDict[peerName].fsmState == _PeerInfoInternal.STATE_REJECT:
			assert self.peerInfoDict[peerName].powerStateWhenInactive == self.POWER_STATE_UNKNOWN
			return self.POWER_STATE_UNKNOWN
		else:
			return self.POWER_STATE_RUNNING

	def doPeerPowerOperationAsync(self, peerName, opName, okFunc, errFunc):
		"""call okFunc when success, call errFunc when failure"""

		assert opName in [ "poweron", "poweroff", "reboot", "wakeup", "suspend", "hibernate", "hybrid-sleep" ]

		if self.peerInfoDict[peerName].opArgPower is not None:
			errFunc(Exception("another power operation is pending"))
			return

		if opName == "poweron":
			if self.getPeerPowerState(peerName) not in [ self.POWER_STATE_UNKNOWN, self.POWER_STATE_POWEROFF ]:
				errFunc(Exception("the current power state of peer doesn't support this power operation"))
				return
			if not self.param.configManager.getHostInfo(peerName).supportPoweron:
				errFunc(Exception("peer doesn't support this power operation"))
				return

			assert False
		elif opName == "wakeup":
			if self.getPeerPowerState(peerName) not in [ self.POWER_STATE_UNKNOWN, self.POWER_STATE_SUSPEND, self.POWER_STATE_HIBERNATE, self.POWER_STATE_HYBRID_SLEEP ]:
				errFunc(Exception("the current power state of peer doesn't support this power operation"))
				return
			if not self.param.configManager.getHostInfo(peerName).supportWakeup:
				errFunc(Exception("peer doesn't support this power operation"))
				return

			assert False
		else:
			if self.peerInfoDict[peerName].fsmState != _PeerInfoInternal.STATE_FULL:
				errFunc(Exception("the current power state of peer doesn't support this power operation"))
				return

			o = SnSysPacketPowerOp()
			o.name = opName
			self._sendObject(peerName, o)

		self.peerInfoDict[peerName].opArgPower = (okFunc, errFunc)

	##### event callback ####

	def onSocketConnected(self, sslSock):
		peerName = SnUtil.getSslSocketPeerName(sslSock)

		# need peer name
		if peerName is None:
			sslSock.close()
			logging.debug("SnPeerManager.onSocketConnected: Fail, no peer name")
			return

		# only peer in self-net is allowed
		if peerName not in self.peerInfoDict:
			sslSock.close()
			logging.debug("SnPeerManager.onSocketConnected: Fail, foreign peer, %s"%(peerName))
			return

		# only one connection between a pair of hosts
		if self.peerInfoDict[peerName].fsmState != _PeerInfoInternal.STATE_NONE:
			sslSock.close()
			logging.debug("SnPeerManager.onSocketConnected: Fail, duplicate connection")
			return

		# send keep-alive packet for every second
		assert sslSock.getsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE) == 0
		sslSock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, 1)
		sslSock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, 1)
		sslSock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPCNT, 100)
		sslSock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)

		# record sock
		oldFsmState = self.peerInfoDict[peerName].fsmState
		self.peerInfoDict[peerName].fsmState = _PeerInfoInternal.STATE_INIT
		self.peerInfoDict[peerName].powerStateWhenInactive = self.POWER_STATE_UNKNOWN
		self.peerInfoDict[peerName].infoObj = None
		self.peerInfoDict[peerName].sock = objsocket(objsocket.SOCKTYPE_SSL_SOCKET, sslSock, self.onSocketRecv, self.onSocketError, self._gcComplete)
		logging.info("SnPeerManager.onSocketConnected: %s", _dbgmsg_peer_state_change(peerName, oldFsmState, self.peerInfoDict[peerName].fsmState))

		# timer operation
		self._timerOperation()

		# send localInfo
		self._sendObject(peerName, self.param.configManager.getVersion())
		self._sendObject(peerName, self.param.configManager.getCfgSerializationObject())
		self._sendObject(peerName, self.param.localManager.getLocalInfo())

	def onSocketRecv(self, sock, packetObj):
		peerName = self._getPeerNameBySock(sock)
		if _type_check(packetObj, SnSysPacket):
			if _type_check(packetObj.data, SnVersion):
				self._recvVerMatch(peerName, packetObj.data)
			elif _type_check(packetObj.data, SnCfgSerializationObject):
				self._recvCfgMatch(peerName, packetObj.data)
			elif _type_check(packetObj.data, SnSysInfo):
				self._recvPeerInfo(peerName, packetObj.data)
			elif _type_check(packetObj.data, SnSysPacketPowerOp):
				logging.debug("SnPeerManager.onSocketRecv: _recvPowerOp")
				self._recvPowerOp(peerName, packetObj.data)
			elif _type_check(packetObj.data, SnSysPacketPowerOpAck):
				logging.debug("SnPeerManager.onSocketRecv: _recvPowerOpAck")
				self._recvPowerOpAck(peerName, packetObj.data)
			elif _type_check(packetObj.data, SnSysPacketPowerStateWhenInactive):
				logging.debug("SnPeerManager.onSocketRecv: _recvPowerStateWhenInactive")
				self._recvPowerStateWhenInactive(peerName, packetObj.data)
			elif _type_check(packetObj.data, SnSysPacketReject):
				self._recvReject(peerName, packetObj.data.message)
			else:
				self._sendReject(peerName, "invalid system packet data format")
		elif _type_check(packetObj, SnDataPacket):
			self.param.localManager.onPeerSockRecv(peerName, packetObj.srcUserName, 
						packetObj.srcModuleName, packetObj.data)
		else:
			self._sendReject(peerName, "invalid packet format, %s"%(packetObj.__class__))

	def onSocketError(self, sock, excObj):
		peerName = self._getPeerNameBySock(sock)

		oldFsmState = self.peerInfoDict[peerName].fsmState
		newFsmState = _PeerInfoInternal.STATE_NONE
		self._peerToShutdown(peerName)
		logging.info("SnPeerManager.onSocketError: %s, %s", str(excObj), _dbgmsg_peer_state_change(peerName, oldFsmState, newFsmState))

		self._timerOperation()

	def onPeerProbe(self):
		for pname, pinfo in self.peerInfoDict.items():
			if pinfo.fsmState == _PeerInfoInternal.STATE_NONE:
				self.clientEndPoint.connect(pname, self.param.configManager.getHostInfo(pname).port)
		return True

	def sendDataObject(self, peerName, srcUserName, srcModuleName, obj):
		if self.peerInfoDict[peerName].fsmState != _PeerInfoInternal.STATE_FULL:
			return

		packetObj = SnDataPacket()
		packetObj.srcUserName = srcUserName
		packetObj.srcModuleName = srcModuleName
		packetObj.data = obj
		self.peerInfoDict[peerName].sock.send(packetObj)

	##### implementation ####

	def _getPeerNameBySock(self, sock):
		for pi, pv in self.peerInfoDict.items():
			if pv.sock == sock:
				return pi
		assert False

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
		logging.info("SnPeerManager._recvVerMatch: %s", _dbgmsg_peer_state_change(peerName, oldFsmState, self.peerInfoDict[peerName].fsmState))

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
		logging.info("SnPeerManager._recvCfgMatch: %s", _dbgmsg_peer_state_change(peerName, oldFsmState, self.peerInfoDict[peerName].fsmState))

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
		logging.info("SnPeerManager._recvPeerInfo: %s", _dbgmsg_peer_state_change(peerName, oldFsmState, self.peerInfoDict[peerName].fsmState))

		# do notify
		self.param.localManager.onPeerChange(peerName, peerInfo)

	def _recvPowerOp(self, peerName, powerOp):
		if powerOp.name not in [ "poweroff", "reboot", "suspend", "hibernate", "hybrid-sleep" ]:
			self._sendReject(peerName, "invalid power operation name \"%s\""%(powerOp.name))
			return

		try:
			dbusObj = dbus.SystemBus().get_object('org.freedesktop.login1', '/org/freedesktop/login1')
			if powerOp.name == "poweroff":
				dbusObj.PowerOff(False, dbus_interface='org.freedesktop.login1.Manager')
			elif powerOp.name == "reboot":
				dbusObj.Reboot(False, dbus_interface='org.freedesktop.login1.Manager')
			elif powerOp.name == "suspend":
				dbusObj.Suspend(False, dbus_interface='org.freedesktop.login1.Manager')
			elif powerOp.name == "hibernate":
				dbusObj.Hibernate(False, dbus_interface='org.freedesktop.login1.Manager')
			elif powerOp.name == "hybrid-sleep":
				dbusObj.HybridSleep(False, dbus_interface='org.freedesktop.login1.Manager')
			else:
				assert False
		except Exception as e:
			o = SnSysPacketPowerOpAck()
			o.error_message = e.message
			self._sendObject(peerName, o)

	def _recvPowerOpAck(self, peerName, powerOpAck):
		opArgPower = self.peerInfoDict[peerName].opArgPower
		if opArgPower is None:
			self._sendReject(peerName, "invalid power operation acknowledgement received")
			return

		self.peerInfoDict[peerName].opArgPower = None
		if powerOpAck.error_message is None:
			opArgPower[0]()
		else:
			opArgPower[1](Exception(powerOpAck.error_message))

	def _recvPowerStateWhenInactive(self, peerName, powerStateWhenInactive):
		if powerStateWhenInactive.name == "poweroff":
			self.peerInfoDict[peerName].powerStateWhenInactive = self.POWER_STATE_POWEROFF
		elif powerStateWhenInactive.name == "rebooting":
			self.peerInfoDict[peerName].powerStateWhenInactive = self.POWER_STATE_REBOOTING
		elif powerStateWhenInactive.name == "suspend":
			self.peerInfoDict[peerName].powerStateWhenInactive = self.POWER_STATE_SUSPEND
		elif powerStateWhenInactive.name == "hibernate":
			self.peerInfoDict[peerName].powerStateWhenInactive = self.POWER_STATE_HIBERNATE
		elif powerStateWhenInactive.name == "hybrid-sleep":
			self.peerInfoDict[peerName].powerStateWhenInactive = self.POWER_STATE_HYBRID_SLEEP
		else:
			self._sendReject(peerName, "invalid power state name \"%s\""%(powerStateWhenInactive.name))

	def _recvReject(self, peerName, rejectMessage):
		logging.error("receive reject, %s, %s", peerName, rejectMessage)

		oldFsmState = self.peerInfoDict[peerName].fsmState
		newFsmState = _PeerInfoInternal.STATE_REJECT
		self._peerToReject(peerName)
		logging.info("SnPeerManager._recvReject: %s", _dbgmsg_peer_state_change(peerName, oldFsmState, newFsmState))

		self._timerOperation()

	def _sendObject(self, peerName, obj):
		packetObj = SnSysPacket()
		packetObj.data = obj
		self.peerInfoDict[peerName].sock.send(packetObj)

	def _sendReject(self, peerName, rejectMessage):
		logging.error("send reject, closing gracefully, %s, %s", peerName, rejectMessage)

		# send reject message
		packetObj = SnSysPacket()
		packetObj.data = SnSysPacketReject()
		packetObj.data.message = rejectMessage
		self.peerInfoDict[peerName].sock.send(packetObj)

		# graceful close, wait reject message to be sent
		self.peerInfoDict[peerName].sock.gracefulClose()

	def _gcComplete(self, sock):
		peerName = self._getPeerNameBySock(sock)

		oldFsmState = self.peerInfoDict[peerName].fsmState
		newFsmState = _PeerInfoInternal.STATE_REJECT
		self._peerToReject(peerName)
		logging.info("SnPeerManager._gcComplete: %s", _dbgmsg_peer_state_change(peerName, oldFsmState, newFsmState))

		self._timerOperation()

	def _peerToShutdown(self, peerName):
		oldState = self.peerInfoDict[peerName].fsmState
	
		# remove peer, don't modify powerStateWhenInactive
		self.peerInfoDict[peerName].sock.close()
		self.peerInfoDict[peerName].fsmState = _PeerInfoInternal.STATE_NONE
		self.peerInfoDict[peerName].infoObj = None
		self.peerInfoDict[peerName].sock = None
		self.peerInfoDict[peerName].opArgPower = None

		# do notify
		if oldState == _PeerInfoInternal.STATE_FULL:
			self.param.localManager.onPeerChange(peerName, None)

	def _peerToReject(self, peerName):
		oldState = self.peerInfoDict[peerName].fsmState
	
		# remove peer
		self.peerInfoDict[peerName].sock.close()
		self.peerInfoDict[peerName].powerStateWhenInactive = self.POWER_STATE_UNKNOWN
		self.peerInfoDict[peerName].fsmState = _PeerInfoInternal.STATE_REJECT
		self.peerInfoDict[peerName].infoObj = None
		self.peerInfoDict[peerName].sock = None
		self.peerInfoDict[peerName].opArgPower = None

		# do notify
		if oldState == _PeerInfoInternal.STATE_FULL:
			self.param.localManager.onPeerChange(peerName, None)

	def _timerOperation(self):
		if any(x for x in self.peerInfoDict.values() if x.sock is None):
			if self.peerProbeTimer is None:
				logging.debug("SnPeerManager._timerOperation: PeerProbeTimer starts")
				interval = self.param.configManager.getPeerProbeInterval()
				self.peerProbeTimer = GObject.timeout_add_seconds(interval, self.onPeerProbe)
		else:
			if self.peerProbeTimer is not None:
				logging.debug("SnPeerManager._timerOperation: PeerProbeTimer stops")
				GLib.source_remove(self.peerProbeTimer)
				self.peerProbeTimer = None

	def _disposeComplete(self):
		logging.debug("SnPeerManager.dispose: End")
		self.disposeCompleteFunc()

class _PeerInfoInternal:
	STATE_NONE = 0
	STATE_INIT = 1
	STATE_VER_MATCH = 2
	STATE_CFG_MATCH = 3
	STATE_FULL = 4
	STATE_REJECT = 5

	fsmState = None							# enum
	powerStateWhenInactive = None			# enum
	infoObj = None							# obj, SnSysInfo
	sock = None								# obj, peer socket
	opArgPower = None						# (okFunc, errFunc)

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

def _type_check(obj, typeobj):
	return str(obj.__class__) == str(typeobj)

