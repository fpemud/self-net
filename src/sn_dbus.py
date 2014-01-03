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

class SelfNetException(dbus.DBusException):
    _dbus_error_name = 'org.fpemud.SelfNet.Exception'

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

	@dbus.service.method('org.fpemud.SelfNet', sender_keyword='sender', 
	                     in_signature='', out_signature='ai')
	def GetPeerList(self, sender=None):
		ret = []
		for po in self.peerList:
			ret.append(po.peerId)
		return ret

	@dbus.service.method('org.fpemud.SelfNet', sender_keyword='sender',
	                     in_signature='', out_signature='st')
	def GetLocalInfo(self, sender=None):
		peerObj = self.param.peerManager.getLocalInfo()
		po = DbusPeerObject(self.param, peerObj, 0)

		assert False
		return None

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

def _getDbusPeerInfoFromPeerInfo(peerInfo):
	pass

