#!/usr/bin/python2
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import os
import socket
import strict_pgs
from sn_conn_local import SnLocalServer
from sn_manager_peer import SnPeerInfo
from sn_manager_peer import SnPeerInfoUser
from sn_manager_peer import SnPeerInfoModule
from sn_manager_peer import SnPacket
from sn_manager_peer import SnReject

class SnLocalManager:

	def __init__(self, param):
		self.param = param
		self.localInfo = self._getLocalInfo()		# SnPeerInfo
		self.coreProxy = None
		self.moduleObjList = []

	def getLocalInfo(self):
		return self.localInfo

	def _onPeerChange(self, peerName, peerInfo):
		"""Called after peer add or peer change"""

		# process module removal
		newList = []

		for mo in self.moduleObjList:
			if mo.getPeerName() != peerName:
				newList.append(mo)
				continue

			found = False
			for mio in peerInfo.moduleList:
				if (mo.getModuleName() == self._getPeerModuleName(mio.moduleName)
						and mo.getUserName() == mio.userName):
					found = True
					break
			if found:
				newList.append(mo)
				continue

			mo.onInactive()

		self.moduleObjList = newList

		# process module add
		for mio in peerInfo.moduleList:
			found = False
			for mo in self.moduleObjList:
				if (mo.getPeerName() == peerName
						and mo.getUserName() == mio.userName
						and mo.getModuleName() == self._getPeerModuleName(mio.moduleName)):
					found = True
					break
			if found:
				continue

			if mio.userName in self.param.configManager.getCfgGlobal().userBlackList:
				continue

			eval("from modules.%s import ModuleObject"%(self._getPeerModuleName(mio.moduleName)))
			mo = ModuleObject(self.coreProxy, peerName, mio.userName)
			mo.onActive()
			self.moduleObjList.append(mo)

	def _onPeerRemove(self, peerName):
		"""Called before peer removal"""

		newList = []
		for mo in self.moduleObjList:
			if mo.getPeerName() == peerName:
				mo.onInactive()
			else:
				newList.add(mo)
		self.moduleObjList = newList

	def _onRecv(self, packetObj):
		"""Called when data packet received from peer"""

		assert isinstance(packetObj, SnDataPacket)
		for mo in self.moduleObjList:
			if (mo.getPeerName() == packetObj.srcPeerName
					and mo.getUserName() == packetObj.srcUserName
					and mo.getModuleName() == self._getPeerModuleName(packetObj.srcModuleName)):
				if isinstance(packetObj.data, SnDataPacketReject):
					mo._onReject(packetObj.data.message)
				else:
					mo._onRecv(packetObj.data)
				break

	def _getLocalInfo(self):
		pgs = strict_pgs.PasswdGroupShadow("/")
		ret = SnPeerInfo()

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
					if uname in self.param.configManager.getCfgGlobal().userBlackList:
						continue
					n = SnCfgModuleInfo()
					n.moduleName = mname
					n.userName = uname
					ret.moduleList.append(n)
			else:
				assert False

		ret.userList = []
		for uname in pgs.getNormalUserList():
			if uname in self.param.configManager.getCfgGlobal().userBlackList:
				continue
			n = SnPeerInfoUser()
			n.userName = uname
			ret.userInfoList.append(n)

		return ret

	def _getPeerModuleName(self, moduleName):
		strList = moduleName.split("-")
		assert len(strList) == 3

		if strList[1] == "server":
			strList[1] = "client"
		elif strList[1] == "client":
			strList[1] = "server"
		else:
			assert False

		return "-".join(strList)

