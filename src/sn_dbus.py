#!/usr/bin/python2
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import os
import shutil
import dbus
import dbus.service
from gi.repository import GObject
from sn_util import SnUtil
from sn_manager_local import SnLocalManager
from sn_manager_local import _ModuleObjInternal			# fixme
from sn_manager_peer import SnPeerManager

################################################################################
# DBus API Docs
################################################################################
#
# ==== Main Application ====
# Service               org.fpemud.SelfNet
# Interface             org.fpemud.SelfNet
# Object path           /
#
# Methods:
# str                 GetWorkState()
# array<peerId:int>   GetPeerList()
# peerId:int          GetPeer(peerName:str)
# array<moduleId:int> GetModuleList()
# moduleId:int        GetModule(peerName:str, userName:str, moduleName:str)
#
# Signals:
# WorkStateChanged(newWorkState:str)
#
# ==== Peer ====
# Service               org.fpemud.SelfNet
# Interface             org.fpemud.SelfNet.Peer
# Object path           /Peers/{peerId:int}
#
# Methods:
# str               GetName()
# str               GetPowerState()
# void              DoPowerOperation(opName:str)
# 
# Signals:
# PowerStateChanged(newPowerState:str)
#
# ==== Module ====
# Service               org.fpemud.SelfNet
# Interface             org.fpemud.SelfNet.Module
# Object path           /Modules/{moduleId:int}
#
# Methods:
# str:str:str       GetKey()
# str:str           GetState()
#
# Signals:
# ModuleStateChanged(newModuleState:str)
#

class DbusMainObject(dbus.service.Object):

	def __init__(self, param):
		self.param = param
		self.peerList = []
		self.moduleList = []

		# initialize peer list
		i = 0
		for pn in self.param.peerManager.getPeerNameList():
			po = DbusPeerObject(self.param, i, pn)
			self.peerList.append(po)
			i = i + 1

		# initialize module list
		i = 0
		for mk in self.param.localManager.getModuleKeyList():
			peerName, userName, moduleName = mk
			mo = DbusModuleObject(self.param, i, peerName, userName, moduleName)
			self.moduleList.append(mo)
			i = i + 1

		# register dbus object path
		bus_name = dbus.service.BusName('org.fpemud.SelfNet', bus=dbus.SystemBus())
		dbus.service.Object.__init__(self, bus_name, '/org/fpemud/SelfNet')

	def release(self):
		self.remove_from_connection()

	@dbus.service.method('org.fpemud.SelfNet', in_signature='', out_signature='s')
	def GetWorkState(self):
		ws = self.param.localManager.getWorkState()
		if ws == SnLocalManager.WORK_STATE_IDLE:
			return "idle"
		elif ws == SnLocalManager.WORK_STATE_WORKING:
			return "working"
		else:
			assert False

	@dbus.service.method('org.fpemud.SelfNet', in_signature='', out_signature='ai')
	def GetPeerList(self):
		ret = []
		for po in self.peerList:
			ret.append(po.peerId)
		return ret

	@dbus.service.method('org.fpemud.SelfNet', in_signature='s', out_signature='i')
	def GetPeer(self, peerName):
		for po in self.peerList:
			if peerName == po.peerName:
				return po.peerId
		return -1

	@dbus.service.method('org.fpemud.SelfNet', in_signature='', out_signature='ai')
	def GetModuleList(self):
		ret = []
		for mo in self.moduleList:
			ret.append(mo.moduleId)
		return ret

	@dbus.service.method('org.fpemud.SelfNet', in_signature='sss', out_signature='i')
	def GetModule(self, peerName, userName, moduleName):
		for mo in self.moduleList:
			if (peerName == mo.peerName and moduleName == mo.moduleName and
					(userName == mo.userName or (userName == "" and mo.userName is None))):
				return mo.moduleId
		return -1

	@dbus.service.signal('org.fpemud.SelfNet', signature='s')
	def WorkStateChanged(self, newWorkState):
		pass

class DbusPeerObject(dbus.service.Object):

	def __init__(self, param, peerId, peerName):
		self.param = param
		self.peerId = peerId
		self.peerName = peerName

		# register dbus object path
		bus_name = dbus.service.BusName('org.fpemud.SelfNet', bus=dbus.SystemBus())
		dbus.service.Object.__init__(self, bus_name, '/org/fpemud/SelfNet/Peers/%d'%(self.peerId))

	def release(self):
		self.remove_from_connection()

	@dbus.service.method('org.fpemud.SelfNet.Peer', sender_keyword='sender',
	                     in_signature='', out_signature='s')
	def GetName(self, sender=None):
		return self.peerName
	                     
	@dbus.service.method('org.fpemud.SelfNet.Peer', sender_keyword='sender',
	                     in_signature='', out_signature='s')
	def GetPowerState(self, sender=None):
		powerStateDict = {
			SnPeerManager.POWER_STATE_UNKNOWN: "unknown",
			SnPeerManager.POWER_STATE_POWEROFF: "poweroff",
			SnPeerManager.POWER_STATE_REBOOTING: "rebooting",
			SnPeerManager.POWER_STATE_SUSPEND: "suspend",
			SnPeerManager.POWER_STATE_HIBERNATE: "hibernate",
			SnPeerManager.POWER_STATE_HYBRID_SLEEP: "hybrid-sleep",
			SnPeerManager.POWER_STATE_RUNNING: "running",
		}
		powerState = self.param.peerManager.getPeerPowerState(self.peerName)
		return powerStateDict[powerState]

	@dbus.service.method('org.fpemud.SelfNet.Peer', sender_keyword='sender',
	                     in_signature='s', out_signature='',
	                     async_callbacks=('reply_handler', 'error_handler'))
	def DoPowerOperation(self, opName, reply_handler, error_handler, sender=None):
		if opName not in [ "poweron", "poweroff", "reboot", "wakeup", "suspend", "hibernate", "hybrid-sleep" ]:
			error_handler(Exception("invalid power operation name \"%s\""%(opName)))
			return
		self.param.peerManager.doPeerPowerOperationAsync(self.peerName, str(opName), reply_handler, error_handler)

	@dbus.service.signal('org.fpemud.SelfNet.Peer', signature='s')
	def PowerStateChanged(self, newPowerState):
		pass

class DbusModuleObject(dbus.service.Object):
	"""For sys module, userName == '' """

	def __init__(self, param, moduleId, peerName, userName, moduleName):
		self.param = param
		self.moduleId = moduleId
		self.peerName = peerName
		self.userName = userName
		self.moduleName = moduleName

		# register dbus object path
		bus_name = dbus.service.BusName('org.fpemud.SelfNet', bus=dbus.SystemBus())
		dbus.service.Object.__init__(self, bus_name, '/org/fpemud/SelfNet/Modules/%d'%(self.moduleId))

	def release(self):
		self.remove_from_connection()

	@dbus.service.method('org.fpemud.SelfNet.Module', sender_keyword='sender',
	                     in_signature='', out_signature='(sss)')
	def GetKey(self, sender=None):
		userName = ""
		if self.userName is not None:
			userName = self.userName
		return (self.peerName, userName, self.moduleName)

	@dbus.service.method('org.fpemud.SelfNet.Module', sender_keyword='sender',
	                     in_signature='', out_signature='(ss)')
	def GetState(self, sender=None):
		moduleStateDict = {
			_ModuleObjInternal.STATE_INIT: "init",
			_ModuleObjInternal.STATE_INACTIVE: "inactive",
			_ModuleObjInternal.STATE_ACTIVE: "active",
			_ModuleObjInternal.STATE_REJECT: "reject",
			_ModuleObjInternal.STATE_PEER_REJECT: "peer-reject",
			_ModuleObjInternal.STATE_EXCEPT: "except",
			_ModuleObjInternal.STATE_PEER_EXCEPT: "peer-except",
		}
		state, failMessage = self.param.localManager.getModuleState(self.peerName, self.userName, self.moduleName)
		return (moduleStateDict[state], failMessage)

