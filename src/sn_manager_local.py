#!/usr/bin/python2
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import os
import shutil
import socket
import logging
import strict_pgs
from gi.repository import GLib

from sn_util import SnUtil
from sn_util import SnSleepNotifier
from sn_module import SnModuleInstance
from sn_module import SnModuleInstanceInitParam
from sn_module import SnModuleInstanceInitException

# fixme: needs to consider user change, both local user change and user change received by peer

class SnSysInfo:
	userList = None					# list<SnSysInfoUser>
	moduleList = None				# list<SnSysInfoModule>

class SnSysInfoUser:
	userName = None					# str

	def __eq__(self, other):
		return isinstance(other, self.__class__) and self.userName == other.userName
	def __ne__(self, other):
		return not self.__eq__(other)
	def __hash__(self):
		return hash(self.userName)

class SnSysInfoModule:
	moduleName = None				# str
	userName = None					# str

	def __eq__(self, other):
		return isinstance(other, self.__class__) and self.moduleName == other.moduleName and self.userName == other.userName
	def __ne__(self, other):
		return not self.__eq__(other)
	def __hash__(self):
		return hash(self.moduleName) ^ hash(self.userName)

class SnDataPacket:
	srcUserName = None				# str, can be None
	srcModuleName = None			# str
	data = None						# object

class SnDataPacketReject:
	message = None					# str

class SnLocalManager:

	WORK_STATE_IDLE = 0
	WORK_STATE_WORKING = 1

	def __init__(self, param):
		logging.debug("SnLocalManager.__init__: Start")

		self.param = param
		self.localInfo = self._getLocalInfo()
		self.moduleObjDict = self._getModuleObjDict()
		self.sleepNotifier = SnSleepNotifier(self.onBeforeSleep, self.onAfterResume)

		GLib.idle_add(self._idleLocalPeerActive)

		logging.debug("SnLocalManager.__init__: End")
		return

	def dispose(self):
		logging.debug("SnLocalManager.dispose: Start")

		# set modules of local peer to inactive state
		if socket.gethostname() in self.moduleObjDict:
			self.onPeerRemove(socket.gethostname())

		# check modules' state
		for peerName, moduleObjList in self.moduleObjDict.items():
			for mo in moduleObjList:
				assert mo.getState() in [ SnModuleInstance.STATE_INIT_FAILED, SnModuleInstance.STATE_INACTIVE ]

		logging.debug("SnLocalManager.dispose: End")
		return

	def getLocalInfo(self):
		return self.localInfo

	def getWorkState(self):
		for moduleObjList in self.moduleObjDict.values():
			for mo in moduleObjList:
				if mo.getWorkState() == SnModuleInstance.WORK_STATE_WORKING:
					return SnModuleInstance.WORK_STATE_WORKING
		return SnModuleInstance.WORK_STATE_IDLE

	##### event callback ####

	def onPeerChange(self, peerName, peerInfo):
		logging.debug("SnLocalManager.onPeerChange: Start, %s", peerName)

		# module inactive
		for mo in self.moduleObjDict[peerName]:
			if not self._matchPeerModuleList(peerInfo, mo):
				if mo.getState() == SnModuleInstance.STATE_INIT_FAILED:
					pass
				elif mo.getState() == SnModuleInstance.STATE_ACTIVE:
					logging.debug("SnLocalManager.onPeerChange: mo active -> inactive start, %s, %s, %s", peerName, mo.getUserName(), mo.getModuleName())
					SnUtil.euidInvoke(mo.getUserName(), mo.onInactive)
					shutil.rmtree(mo.getInitParam().tmpDir, True)
					mo.setState(SnModuleInstance.STATE_INACTIVE)
					logging.debug("SnLocalManager.onPeerChange: mo active -> inactive end")
				elif mo.getState() == SnModuleInstance.STATE_INACTIVE:
					pass
				elif mo.getState() == SnModuleInstance.STATE_REJECT:
					logging.debug("SnLocalManager.onPeerChange: mo reject -> inactive start, %s, %s, %s", peerName, mo.getUserName(), mo.getModuleName())
					mo.setState(SnModuleInstance.STATE_INACTIVE)
					logging.debug("SnLocalManager.onPeerChange: mo reject -> inactive end")
				else:
					assert False

		# module active
		for mio in peerInfo.moduleList:
			mo = self._findModuleList(self.moduleObjDict[peerName], mio)
			if mo is not None:
				if mo.getState() == SnModuleInstance.STATE_INIT_FAILED:
					pass
				elif mo.getState() == SnModuleInstance.STATE_ACTIVE:
					pass
				elif mo.getState() == SnModuleInstance.STATE_INACTIVE:
					logging.debug("SnLocalManager.onPeerChange: mo inactive -> active start, %s, %s, %s", peerName, mo.getUserName(), mo.getModuleName())
					mo.setState(SnModuleInstance.STATE_ACTIVE)
					SnUtil.euidInvoke(mo.getUserName(), mo.onActive)
					logging.debug("SnLocalManager.onPeerChange: mo inactive -> active end")
				elif mo.getState() == SnModuleInstance.STATE_REJECT:
					pass
				else:
					assert False

		logging.debug("SnLocalManager.onPeerChange: End")
		return

	def onPeerRemove(self, peerName):
		logging.debug("SnLocalManager.onPeerRemove: Start, %s", peerName)

		for mo in self.moduleObjDict[peerName]:
			if mo.getState() == SnModuleInstance.STATE_INIT_FAILED:
				pass
			elif mo.getState() == SnModuleInstance.STATE_ACTIVE:
				logging.debug("SnLocalManager.onPeerRemove: mo active -> inactive start, %s, %s, %s", peerName, mo.getUserName(), mo.getModuleName())
				SnUtil.euidInvoke(mo.getUserName(), mo.onInactive)
				shutil.rmtree(mo.getInitParam().tmpDir, True)
				mo.setState(SnModuleInstance.STATE_INACTIVE)
				logging.debug("SnLocalManager.onPeerRemove: mo active -> inactive end")
			elif mo.getState() == SnModuleInstance.STATE_INACTIVE:
				pass
			elif mo.getState() == SnModuleInstance.STATE_REJECT:
				logging.debug("SnLocalManager.onPeerRemove: mo reject -> inactive start, %s, %s, %s", peerName, mo.getUserName(), mo.getModuleName())
				mo.setState(SnModuleInstance.STATE_INACTIVE)
				logging.debug("SnLocalManager.onPeerRemove: mo reject -> inactive end")
			else:
				assert False

		logging.debug("SnLocalManager.onPeerRemove: End")
		return

	def onPacketRecv(self, peerName, userName, srcModuleName, data):
		logging.debug("SnLocalManager.onPacketRecv: Start, %s, %s, %s", peerName, userName, srcModuleName)

		moduleName = self._getMappedModuleName(srcModuleName)
		for mo in self.moduleObjDict[peerName]:
			if mo.getUserName() == userName and mo.getModuleName() == moduleName:
				assert mo.getState() == SnModuleInstance.STATE_ACTIVE

				if self._typeCheck(data, SnDataPacketReject):
					SnUtil.euidInvoke(mo.getUserName(), mo.onReject, data.message)
					SnUtil.euidInvoke(mo.getUserName(), mo.onInactive)
					shutil.rmtree(mo.getInitParam().tmpDir, True)
					mo.setState(SnModuleInstance.STATE_REJECT)
				else:
					SnUtil.euidInvoke(mo.getUserName(), mo.onRecv, data)

				logging.debug("SnLocalManager.onPacketRecv: End")
				return
		assert False

	def onBeforeSleep(self, sleepType):
		pass

	def onAfterResume(self, sleepType):
		pass

	##### implementation ####

	def _sendObject(self, peerName, userName, moduleName, obj):
		if peerName == socket.gethostname():
			GLib.idle_add(self._idleLocalPeerRecv, peerName, userName, moduleName, obj)
		else:
			self.param.peerManager._sendDataObject(peerName, userName, moduleName, obj)

	def _sendReject(self, peerName, userName, moduleName, rejectMessage):
		# record to log
		logging.warning("send reject, module closing gracefully, %s, %s, %s, %s", peerName, userName, moduleName, rejectMessage)

		# send reject message
		rejectObj = SnDataPacketReject()
		rejectObj.message = rejectMessage
		if peerName == socket.gethostname():
			GLib.idle_add(self._idleLocalPeerRecv, peerName, userName, moduleName, rejectObj)
		else:
			self.param.peerManager._sendDataObject(peerName, userName, moduleName, rejectObj)

		GLib.idle_add(self._gcComplete, peerName, userName, moduleName)

	def _gcComplete(self, peerName, userName, moduleName):
		logging.warning("module graceful close complete, %s, %s, %s", peerName, userName, moduleName)

		for mo in self.moduleObjDict[peerName]:
			if mo.getUserName() == userName and mo.getModuleName() == moduleName:
				SnUtil.euidInvoke(mo.getUserName(), mo.onInactive)
				shutil.rmtree(mo.getInitParam().tmpDir, True)
				mo.setState(SnModuleInstance.STATE_REJECT)
				return False
		assert False

	def _idleLocalPeerActive(self):
		if socket.gethostname() in self.moduleObjDict:
			self.onPeerChange(socket.gethostname(), self.localInfo)
		return False

	def _idleLocalPeerRecv(self, peerName, userName, moduleName, data):
		self.onPacketRecv(peerName, userName, moduleName, data)
		return False

	def _getLocalInfo(self):
		pgs = strict_pgs.PasswdGroupShadow("/")
		ret = SnSysInfo()

		ret.userList = []
		for uname in pgs.getNormalUserList():
			if uname in self.param.configManager.getUserBlackList():
				continue
			n = SnSysInfoUser()
			n.userName = uname
			ret.userList.append(n)

		ret.moduleList = []
		for mname in self.param.configManager.getModuleNameList():
			mInfo = self.param.configManager.getModuleInfo(mname)
			if mInfo.moduleScope == "sys":
				n = SnSysInfoModule()
				n.moduleName = mname
				n.userName = None
				ret.moduleList.append(n)
			elif mInfo.moduleScope == "usr":
				for uname in pgs.getNormalUserList():
					if uname in self.param.configManager.getUserBlackList():
						continue
					n = SnSysInfoModule()
					n.moduleName = mname
					n.userName = uname
					ret.moduleList.append(n)
			else:
				assert False

		return ret

	def _getModuleObjDict(self):
		"""Create a full module object collection"""

		pgs = strict_pgs.PasswdGroupShadow("/")
		ret = dict()

		# create self.moduleObjDict, invoke SnModuleInstance.onInit
		for pname in self.param.configManager.getHostNameList():
			moduleObjList = []
			for mname in self.param.configManager.getModuleNameList():
				minfo = self.param.configManager.getModuleInfo(mname)

				if (pname == socket.gethostname() and
						not minfo.moduleObj.getPropDict().get("allow-local-peer", False)):
					continue

				exec("from %s import ModuleInstanceObject"%(mname.replace("-", "_")))
				if minfo.moduleScope == "sys":
					initParam = SnModuleInstanceInitParam()
					initParam.coreObj = self
					initParam.classObj = minfo.moduleObj
					initParam.paramDict = minfo.moduleParamDict
					initParam.peerName = pname
					initParam.userName = None
					initParam.tmpDir = os.path.join(self.param.tmpDir, mname)
					mo = ModuleInstanceObject(initParam)
					logging.debug("SnLocalManager._getModuleObjDict: mo init, %s, %s", pname, mo.getModuleName())
					try:
						SnUtil.euidInvoke(mo.getUserName(), mo.onInit)
						mo.setState(SnModuleInstance.STATE_INACTIVE)
						logging.debug("SnLocalManager._getModuleObjDict: mo init end")
					except SnModuleInstanceInitException as e:
						mo.setState(SnModuleInstance.STATE_INIT_FAILED)
						mo.setInitFailMessage(e.message)
						logging.debug("SnLocalManager._getModuleObjDict: mo init failed, %s", e.message)
					moduleObjList.append(mo)
				elif minfo.moduleScope == "usr":
					for uname in pgs.getNormalUserList():
						if uname in self.param.configManager.getUserBlackList():
							continue

						initParam = SnModuleInstanceInitParam()
						initParam.coreObj = self
						initParam.classObj = minfo.moduleObj
						initParam.paramDict = minfo.moduleParamDict
						initParam.peerName = pname
						initParam.userName = uname
						initParam.tmpDir = os.path.join(self.param.tmpDir, "%s-%s"%(mname, uname))
						mo = ModuleInstanceObject(initParam)
						logging.debug("SnLocalManager._getModuleObjDict: mo init, %s, %s, %s", pname, uname, mo.getModuleName())
						try:
							SnUtil.euidInvoke(mo.getUserName(), mo.onInit)
							mo.setState(SnModuleInstance.STATE_INACTIVE)
							logging.debug("SnLocalManager._getModuleObjDict: mo init end")
						except SnModuleInstanceInitException as e:
							mo.setState(SnModuleInstance.STATE_INIT_FAILED)
							mo.setInitFailMessage(e.message)
							logging.debug("SnLocalManager._getModuleObjDict: mo init failed, %s", e.message)
						moduleObjList.append(mo)
				else:
					assert False
			ret[pname] = moduleObjList

		return ret

	def _matchPeerModuleList(self, peerInfo, mo):
		for mio in peerInfo.moduleList:
			if mo.getUserName() == mio.userName and mo.getModuleName() == self._getMappedModuleName(mio.moduleName):
				return True
		return False

	def _findModuleList(self, moduleObjList, mio):
		for mo in moduleObjList:
			if mo.getUserName() == mio.userName and mo.getModuleName() == self._getMappedModuleName(mio.moduleName):
				return mo
		return None

	def _getMappedModuleName(self, moduleName):
		strList = moduleName.split("-")
		if strList[1] == "server":
			strList[1] = "client"
		elif strList[1] == "client":
			strList[1] = "server"
		return "-".join(strList)

	def _typeCheck(self, obj, typeobj):
		return str(obj.__class__) == str(typeobj)

