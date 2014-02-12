#!/usr/bin/python2
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import os
import shutil
import dbus
import dbus.service
from gi.repository import GObject
from sn_util import SnUtil

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
# array<peerId:int> GetPeerList()
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
# PeerStateChanged(peerId:int)
#

class DbusMainObject(dbus.service.Object):

	def __init__(self, param):
		self.param = param
		self.peerList = []

		# initialize peer list
		i = 0
		for pn in self.param.peerManager.getPeerNameList():
			po = DbusPeerObject(self.param, pn, i)
			self.peerList.append(po)
			i = i + 1

		# register dbus object path
		bus_name = dbus.service.BusName('org.fpemud.SelfNet', bus=dbus.SystemBus())
		dbus.service.Object.__init__(self, bus_name, '/org/fpemud/SelfNet')

	def release(self):
		self.remove_from_connection()

	@dbus.service.method('org.fpemud.SelfNet', in_signature='', out_signature='ai')
	def GetPeerList(self):
		ret = []
		for po in self.peerList:
			ret.append(po.peerId)
		return ret

class DbusPeerObject(dbus.service.Object):

	def __init__(self, param, peerId, peerName):
		self.param = param
		self.peerId = peerId
		self.peerName = peerName

		# register dbus object path
		bus_name = dbus.service.BusName('org.fpemud.SelfNet', bus=dbus.SystemBus())
		dbus.service.Object.__init__(self, bus_name, '/org/fpemud/SelfNet/Peer/%d'%(self.peerId))

	def release(self):
		self.remove_from_connection()

	@dbus.service.method('org.fpemud.SelfNet.Peer', sender_keyword='sender',
	                     in_signature='', out_signature='s')
	def GetName(self, sender=None):
		return self.peerName
	                     
	@dbus.service.method('org.fpemud.SelfNet.Peer', sender_keyword='sender',
	                     in_signature='', out_signature='s')
	def GetPowerState(self, sender=None):
		"""powerState values:
		     "unknown"
		     "running"
		     "poweroff"
		     "restarting"
		     "suspend"
		     "hibernate"
		     "hybrid-sleep"
		"""
	
		peerInfo = self.param.peerManager.getPeerInfo(self.peerName)
		if peerInfo.powerState == SnPeerManager.POWER_STATE_UNKNOWN:
			return "unknown"
		elif peerInfo.powerState == SnPeerManager.POWER_STATE_RUNNING:
			return "running"
		elif peerInfo.powerState == SnPeerManager.POWER_STATE_POWEROFF:
			return "poweroff"
		elif peerInfo.powerState == SnPeerManager.POWER_STATE_RESTARTING:
			return "restarting"
		elif peerInfo.powerState == SnPeerManager.POWER_STATE_SUSPEND:
			return "suspend"
		elif peerInfo.powerState == SnPeerManager.POWER_STATE_HIBERNATE:
			return "hibernate"
		elif peerInfo.powerState == SnPeerManager.POWER_STATE_HYBRID_SLEEP:
			return "hybrid-sleep"
		else:
			assert False

	@dbus.service.method('org.fpemud.SelfNet.Peer', sender_keyword='sender',
	                     in_signature='s', out_signature='')
	def DoPowerOperation(self, sender=None, opName):
		"""opName values:
		     "poweron"
		     "poweroff"
		     "restart"
		     "suspend"
		     "hibernate"
		     "hybrid-sleep"
		"""

		if opName == "poweron":
			self.param.peerManager.peerPowerOperation(self.peerName, SnPeerManager.POWER_OP_POWERON)
		elif opName == "poweroff":
			self.param.peerManager.peerPowerOperation(self.peerName, SnPeerManager.POWER_OP_POWEROFF)
		elif opName == "restart":
			self.param.peerManager.peerPowerOperation(self.peerName, SnPeerManager.POWER_OP_RESTART)
		elif opName == "suspend":
			self.param.peerManager.peerPowerOperation(self.peerName, SnPeerManager.POWER_OP_SUSPEND)
		elif opName == "hibernate":
			self.param.peerManager.peerPowerOperation(self.peerName, SnPeerManager.POWER_OP_HIBERNATE)
		elif opName == "hybrid-sleep":
			self.param.peerManager.peerPowerOperation(self.peerName, SnPeerManager.POWER_OP_HYBRID_SLEEP)
		else:
			assert False

