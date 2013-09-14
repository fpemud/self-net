#!/usr/bin/python2
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

from gi.repository import GObject
from sn_config_manager import SnPeerInfo

class SnPeer(GObject.GObject):

	__gsignals__ = {
		'activated': (GObject.SIGNAL_RUN_FIRST, None, ()),
		'inactivated': (GObject.SIGNAL_RUN_FIRST, None, ()),
		'socket-connected': (GObject.SIGNAL_RUN_FIRST, None, ()),
		'socket-disconnected': (GObject.SIGNAL_RUN_FIRST, None, ()),
	}

	def __init__(self, param, peerName):
		GObject.GObject.__init__(self)

		self.peerName = peerName
		self.peerUser = ""

		self.peerInfo = SnPeerInfo()
		self.peerInfo.name = self.peerName

		self.peerSocket = None
		self.peerSocketBak = None

	def getName(self):
		return self.peerName

	def isActive(self):
		return False

	def getInfo(self):
		return self.peerInfo

	def getSocket(self, serviceName, connMedia, connIntf):
		"""connMedia: net, removable-storage
		   connIntf: socket, bulk"""
		return None

GObject.type_register(SnPeer)

