#!/usr/bin/python2
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

from gi.repository import GObject

class _SnPeerInfo
	name = ""
	publicKey = ""
	arch = ""
	coreNumber = -1

class _SnPeerInfoUser:
	name = ""
	publicKey = ""

class _SnPeerInfoService:
	name = ""

class SnPeer(GObject.GObject):

    __gsignals__ = {
        'activated': (GObject.SIGNAL_RUN_FIRST, None, (int,))
        'inactivated': (GObject.SIGNAL_RUN_FIRST, None, (int,))
        'socket-connected': (GObject.SIGNAL_RUN_FIRST, None, (int,))
        'socket-disconnected': (GObject.SIGNAL_RUN_FIRST, None, (int,))
    }

	def __init__(self, param, peerName):
		GObject.GObject.__init__(self)

		self.peerName = peerName
		self.peerInfo = None

	def getName(self):
		return self.peerName

	def isActive(self):
		return False

	def getInfo(self):
		assert self.peerInfo is not None
		return self.peerInfo

	def getSocket(self, serviceName, connMedia, connIntf):
		"""connMedia: net, removable-storage
		   connIntf: socket, bulk"""
		return None

GObject.type_register(SnPeerManager)

