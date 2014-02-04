#!/usr/bin/python2
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import os
import socket
import strict_pgs

import flogging
from sn_manager_peer import SnPeerInfo
from sn_manager_peer import SnPeerInfoUser
from sn_manager_peer import SnPeerInfoModule

class SnLocalManager:

	def __init__(self, param):
		self.param = param
		self.localInfo = self._getLocalInfo()		# SnPeerInfo
		self.coreProxy = None
		self.moduleObjDict = dict()

	def getLocalInfo(self):
		return self.localInfo

	##### event callback ####

	def onPeerChange(self, peerName):
		flogging.functionStart(peerName)

		peerInfo = self.param.peerManager.getPeerInfo(peerName)

		# process module removal
		for mk, mo in self.moduleObjDict.items():
			found = False
			for mio in peerInfo.moduleList:
				if mk == _ModuleKey.newByPeer(peerName, mio.userName, mio.moduleName):
					found = True
					break
			if found:
				continue

			flogging.debug("mo remove start, %s", mk)
			mo.onInactive()
			del self.moduleObjDict[mk]
			flogging.debug("mo remove end")

		# process module add
		for mio in peerInfo.moduleList:
			newmk = _ModuleKey.newByPeer(peerName, mio.userName, mio.moduleName)

			if newmk in self.moduleObjDict:
				continue
			if newmk.userName in self.param.configManager.getUserBlackList():
				continue
			if newmk.moduleName not in self.param.configManager.getModuleNameList():
				continue
			if not self.param.configManager.getModuleInfo(newmk.moduleName).enable:
				continue

			flogging.debug("newmo add start, %s", newmk)
			eval("from modules.%s import ModuleObject"%(newmk.moduleName.replace("-", "_")))
			newmo = ModuleObject(self.coreProxy, peerName, newmk.userName, newmk.moduleName)
			newmo.onActive()
			self.moduleObjDict[newmk] = newmo
			flogging.debug("newmo add end")

		flogging.functionEnd()

	def onPeerRemove(self, peerName):
		flogging.functionStart(peerName)

		for mk, mo in self.moduleObjDict.items():
			if mk.peerName == peerName:
				flogging.debug("mo remove start, %s", mk)
				mo.onInactive()
				del self.moduleObjDict[mk]
				flogging.debug("mo remove end, %s", mk)

		flogging.functionEnd()

	def onRecv(self, peerName, userName, srcModuleName, data):
		flogging.functionStart(peerName, userName, srcModuleName)

		mk = _ModuleKey.newByPeer(peerName, userName, srcModuleName)
		self.moduleObjDict[mk]._onRecv(data)

		flogging.functionEnd()

	def onReject(self, peerName, userName, srcModuleName, rejectMessage):
		flogging.functionStart(peerName, userName, srcModuleName)

		mk = _ModuleKey.newByPeer(peerName, userName, srcModuleName)
		self.moduleObjDict[mk]._onReject(rejectMessage)

		flogging.functionEnd()

	##### implementation ####

	def _getLocalInfo(self):
		pgs = strict_pgs.PasswdGroupShadow("/")
		ret = SnPeerInfo()

		ret.userList = []
		for uname in pgs.getNormalUserList():
			if uname in self.param.configManager.getUserBlackList():
				continue
			n = SnPeerInfoUser()
			n.userName = uname
			ret.userInfoList.append(n)

		ret.moduleList = []
		for mname in self.param.configManager.getModuleNameList(None, None):
			mInfo = self.param.configManager.getModuleInfo(mname)
			if mInfo.enable is not True:
				continue

			if mInfo.moduleType == "sys":
				n = SnCfgModuleInfo()
				n.moduleName = mname
				n.userName = None
				ret.moduleList.append(n)
			elif mInfo.moduleType == "usr":
				for uname in pgs.getNormalUserList():
					if uname in self.param.configManager.getUserBlackList():
						continue
					n = SnCfgModuleInfo()
					n.moduleName = mname
					n.userName = uname
					ret.moduleList.append(n)
			else:
				assert False

		return ret

class _ModuleKey:

	peerName = None			# str
	userName = None			# str
	moduleName = None		# str

	@staticmethod
	def newBySelf(peerName, userName, moduleName):
		self.peerName = peerName
		self.userName = userName
		self.moduleName = moduleName

	@staticmethod
	def newByPeer(peerName, userName, moduleName):
		self.peerName = peerName
		self.userName = userName

		strList = moduleName.split("-")
		assert len(strList) == 3

		if strList[1] == "server":
			strList[1] = "client"
		elif strList[1] == "client":
			strList[1] = "server"
		else:
			assert False

		self.moduleName = "-".join(strList)

	def __eq__(self, other):
		return (isinstance(other, self.__class__)
					and self.peerName == other.peerName
					and self.userName == other.userName
					and self.moduleName == other.moduleName)
	def __ne__(self, other):
		return not self.__eq__(other)
	def __hash__(self):
		return hash(self.peerName) ^ hash(self.userName) ^ hash(self.moduleName)

