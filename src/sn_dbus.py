#!/usr/bin/python2
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import os
import shutil
import dbus
import dbus.service
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
# Signals:
# PeerListChanged(changeData)
#
# ==== Network ====
# Service               org.fpemud.SelfNet
# Interface             org.fpemud.SelfNet.Peer
# Object path           /Peer/{peerId:int}
#
# Methods:
# bool              IsActive()
# peerInfo:st       GetPeerInfo()
# connInfo:st		GetPeerConn(userName, serviceName)
# 
# Signals:
# Activated()
# Inactivated()
# PeerInfoChanged(changeData)
# PeerConnChanged(changeData)
#

class SelfNetException(dbus.DBusException):
    _dbus_error_name = 'org.fpemud.SelfNet.Exception'

class DbusMainObject(dbus.service.Object):

	def __init__(self, param):
		self.param = param

		self.peerObjList = []
		self._updatePeerList()

		# register dbus object path
		bus_name = dbus.service.BusName('org.fpemud.SelfNet', bus=dbus.SystemBus())
		dbus.service.Object.__init__(self, bus_name, '/org/fpemud/SelfNet')

	def release(self):
		self.remove_from_connection()

	@dbus.service.method('org.fpemud.SelfNet', sender_keyword='sender', 
	                     in_signature='s', out_signature='i')
	def GetPeerList(self, networkType, sender=None):
		# get user id
		uid = SnUtil.dbusGetUserId(self.connection, sender)

		return self.param.configManager.getCfgPeerList()

	def _updatePeerList(self):


		for pi in self.param.configManager.getCfgPeerList():
			np = DbusPeerObject(pi, )
			self.peerObjList.append(


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
		# check user id
		SnUtil.dbusCheckUserId(self.connection, sender, self.uid)

		assert False
		return vmId

	@dbus.service.method('org.fpemud.VirtService.Network', sender_keyword='sender',
	                     in_signature='i')
	def GetPeerInfo(self, sender=None):
		# check user id
		SnUtil.dbusCheckUserId(self.connection, sender, self.uid)

		assert False
		return None

	@dbus.service.method('org.fpemud.VirtService.Network', sender_keyword='sender',
	                     in_signature='ss', out_signature='st')
	def GetPeerConn(self, sender=None):
		# check user id
		SnUtil.dbusCheckUserId(self.connection, sender, self.uid)

		assert False
		return None

class DbusPeerInfo:
	name = ""
	publicKey = ""
	userList = []
	serviceList = []

class DbusPeerInfoUser:
	name = ""
	publicKey = ""

class DbusPeerInfoService:
	name = ""

class DbusPeerConn:
	connSocket = None
	connBulk = None



