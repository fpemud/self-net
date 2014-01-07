#!/usr/bin/python2
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import os
import socket
import strict_pgs
from gi.repository import GObject

class SnAppInfo:
	userName = None			# str, null means system
	appName = None			# str
	agentOrClient = None	# bool

class SnLocalManager(GObject.GObject):

	__gsignals__ = {
		'application_add': (GObject.SIGNAL_RUN_LAST, GObject.TYPE_NONE, ()),
		'application_delete': (GObject.SIGNAL_RUN_LAST, GObject.TYPE_NONE, ()),
	}

	def __init__(self, param):
		GObject.GObject.__init__(self)

		# create veriables
		self.param = param
		self.localInfo = None			# SnPeerInfo

		# update local info
		self._updateLocalInfo()

	def getLocalInfo(self):
		return self.localInfo

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
		ret.systemAppList = []
		ret.userInfoList = []

		pgs = strict_pgs.PasswdGroupShadow("/")
		for uname in pgs.getNormalUserList():
			if uname in self.param.configManager.getCfgGlobal().userBlackList:
				continue

			uo = SnPeerInfoUser()
			uo.userName = uname
			uo.userAppList = []

			ret.userInfoList.append(uo)

		return ret

