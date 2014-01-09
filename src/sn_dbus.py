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
# array<peerId:int> GetActivePeerList()
# peerInfo:st		GetLocalInfo()
#
# ==== Network ====
# Service               org.fpemud.SelfNet
# Interface             org.fpemud.SelfNet.Peer
# Object path           /Peers/{peerId:int}
#
# Methods:
# bool              IsActive()
# peerInfo:st       GetPeerInfo()
# 
# Signals:
# Activated()
# Inactivated()
# PeerInfoChanged(changeData)
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

	@dbus.service.method('org.fpemud.SelfNet', in_signature='', out_signature='ai')
	def GetActivePeerList(self):
		ret = []
		for po in self.peerList:
			if self.param.peerManager.isPeerActive(po.peerName):
				ret.append(po.peerId)
		return ret

	@dbus.service.method('org.fpemud.SelfNet', sender_keyword='sender',
	                     in_signature='', out_signature='(sa(sb)a(sa(sb)))')
	def GetLocalInfo(self, sender=None):
		uname = 
		peerInfo = self.param.localManager.getLocalInfo()
		return _newDbusPeerInfo("localhost", peerInfo, "root")

class DbusPeerObject(dbus.service.Object):

	def __init__(self, param, peerName, peerId):
		self.param = param
		self.peerName = peerName
		self.peerId = peerId

		# register dbus object path
		bus_name = dbus.service.BusName('org.fpemud.SelfNet', bus=dbus.SystemBus())
		dbus.service.Object.__init__(self, bus_name, '/org/fpemud/SelfNet/Peer/%d'%(self.peerId))

	def release(self):
		self.remove_from_connection()

	@dbus.service.method('org.fpemud.SelfNet.Peer', sender_keyword='sender',
	                     in_signature='', out_signature='b')
	def IsActive(self, sender=None):
		return self.param.peerManager.isPeerActive(self.peerName)

	@dbus.service.method('org.fpemud.SelfNet.Peer', sender_keyword='sender',
	                     in_signature='', out_signature='(sa(sb)a(sa(sb)))')
	def GetPeerInfo(self, sender=None):
		peerInfo = self.param.peerManager.getPeerInfo(self.peerName)
		if peerInfo is None:
			return None
		else:
			return _newDbusPeerInfo(self.peerName, peerInfo, "root")

def _newDbusPeerInfo(peerName, peerInfo, curUser):
	"""PeerInfo sent through dbus is represented by tuple
	   dbusPeerInfo: (s:peerName, a:appList)
	   appList element: (s:appName, b:agentOrClient)"""

	appList = []
	if curUser is None:
		for i in peerInfo.systemAppList:
			i2 = (i.appName, i.agentOrClient)
			appList.append(i2)
	else:
		for i in peerInfo.userInfoList:
			if curUser == i.userName:
				for j in i.userAppList:
					j2 = (j.appName, j.agentOrClient)
					appList.append(j2)

	ret = (peerName, peerState, appList, userInfoList)
	return ret

