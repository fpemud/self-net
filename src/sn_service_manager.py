#!/usr/bin/python2
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import os
import socket
import pyinotify
from gi.repository import GObject

class SnCfgService:
	user = None
	name = None

class SnServiceManager(GObject.GObject):

	__gsignals__ = {
		'service_add': (GObject.SIGNAL_RUN_LAST, GObject.TYPE_NONE, ()),
		'service_delete': (GObject.SIGNAL_RUN_LAST, GObject.TYPE_NONE, ()),
	}

	def __init__(self, param):
		GObject.GObject.__init__(self)

		self.param = param
		self.hostDict = dict()
		self.serviceDict = dict()

		self._checkCertFiles()
		self._parseHostsFile()

	def addService(self, userName, serviceName, serviceObj):
		key = (userName, serviceName)
		assert key not in self.serviceDict
		self.serviceDict[key] = serviceObj

	def removeService(self, userName, serviceName):
		key = (userName, serviceName)
		self.serviceDict.remove(key)

	def getService(self, userName, serviceName):
		key = (userName, serviceName)
		assert key in self.serviceDict
		self.serviceDict[key]

	def getLocalInfo(self):
		return SnPeerInfo()				# fixme

