#!/usr/bin/python2
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import os
import socket
import strict_pgs
from gi.repository import GObject

class SnAgentInfo:
	serviceName = None		# str
	priviledged = None		# bool
	forUser = None			# str, null means system

class SnClientInfo:
	serviceName = None		# str
	user = None				# str, null means system

class SnServKey:
	user = None				# str, null means system
	serviceName = None		# str
	agentOrclient = None	# bool

class SnLocalManager(GObject.GObject):

	__gsignals__ = {
		'service_add': (GObject.SIGNAL_RUN_LAST, GObject.TYPE_NONE, ()),
		'service_delete': (GObject.SIGNAL_RUN_LAST, GObject.TYPE_NONE, ()),
	}

	def __init__(self, param):
		GObject.GObject.__init__(self)

		# create veriables
		self.param = param
		self.serviceDict = dict()
		self.localInfo = None

		# register local info monitors


		# update local info
		self._updateLocalInfo()

	def getLocalInfo(self):
		return self.localInfo

	def dataToService(self, key, data):
		pass

	def _updateLocalInfo(self):
		oldInfo = self.localInfo
		newInfo = self._getLocalInfo()

		# special case
		if oldInfo is None:
			self.localInfo = newInfo
			return

		# oldInfo and newInfo is same
		if deep_eq(oldInfo, newInfo):
			return

		# replace and notify
		self.localInfo = newInfo

	def _getLocalInfo(self):
		ret = SnPeerInfo()
		ret.systemAgentList = []
		ret.systemClientList = []
		ret.userInfoList = []

		pgs = strict_pgs.PasswdGroupShadow("/")
		for uname in pgs.getNormalUserList():
			if uname in self.param.configManager.getCfgGlobal().userBlackList:
				continue

			uo = SnPeerInfoUser()
			uo.userId = pwd.getpwnam(uname).pw_uid
			uo.userName = uname
			uo.userAgentList = []
			uo.userClientList = []

			ret.userInfoList.append(uo)

		return ret


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

