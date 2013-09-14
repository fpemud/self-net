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
# array<peerId:int> GetPeerList()									returns peer id list
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
		self.peerList = []

		# initialize peer list and connect peer event
		i = 0
		for peerObj in self.param.peerManager.getPeerList():
			po = DbusPeerObject(self.param, peerObj, i)
			self.peerList.append(po)
			i = i + 1
		self.param.peerManager.connect("peer_add", self._onPeerAdd)
		self.param.peerManager.connect("peer_delete", self._onPeerDelete)

		# register dbus object path
		bus_name = dbus.service.BusName('org.fpemud.SelfNet', bus=dbus.SystemBus())
		dbus.service.Object.__init__(self, bus_name, '/org/fpemud/SelfNet')

	def release(self):
		self.remove_from_connection()

	@dbus.service.method('org.fpemud.SelfNet', sender_keyword='sender', 
	                     in_signature='', out_signature='ai')
	def GetPeerList(self, sender=None):
		ret = []
		for po in self.peerList:
			ret.append(po.peerId)
		return ret

	def _onPeerAdd(self, peerObj):
		i = 0
		for p in self.peerList:
			i = max(p.peerId, i)
		po = DbusPeerObject(self.param, peerObj, i + 1)
		self.peerList.append(po)

	def _onPeerDelete(self, peerName):
		for p in self.peerList:
			if p.peerObj.getName() == peerName:
				p.release()
				self.peerList.remove(p)
				return
		assert False
				
class DbusPeerObject(dbus.service.Object):

	def __init__(self, param, peerObj, peerId):
		self.param = param
		self.peerObj = peerObj
		self.peerId = peerId

		# register dbus object path
		bus_name = dbus.service.BusName('org.fpemud.SelfNet', bus=dbus.SystemBus())
		dbus.service.Object.__init__(self, bus_name, '/org/fpemud/SelfNet/Peer/%d'%(self.peerId))

	def release(self):
		self.remove_from_connection()

	@dbus.service.method('org.fpemud.SelfNet.Peer', sender_keyword='sender',
	                     in_signature='', out_signature='b')
	def IsActive(self, sender=None):
		return self.peerObj.isActive()

	@dbus.service.method('org.fpemud.SelfNet.Peer', sender_keyword='sender',
	                     in_signature='')
	def GetPeerInfo(self, sender=None):
		pi = self.peerObj.getInfo()
		if pi is None:
			return None

		ret = DbusPeerInfo()
		ret.name = pi.name
		return ret

	@dbus.service.method('org.fpemud.SelfNet.Peer', sender_keyword='sender',
	                     in_signature='ss', out_signature='st')
	def GetPeerConn(self, userName, serviceName, sender=None):
		assert False
		return None

class DbusPeerInfo:
	name = ""
	publicKey = ""
	isActive = False
	userList = []
	serviceList = []

class DbusPeerInfoUser:
	name = ""
	publicKey = ""

class DbusPeerInfoService:
	name = ""
	status = ""

class DbusPeerConn:
	connSocket = None
	connBulk = None



