#!/usr/bin/python2
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import os
import shutil
import socket
import logging
import traceback
import strict_pgs
from gi.repository import GLib

from sn_util import SnUtil
from sn_util import SnSleepNotifier
from sn_conn_local import SnLocalServer
from sn_module import SnModuleInstance
from sn_module import SnRejectException

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

class SnDataPacketExcept:
	pass

class SnLocalManager:

	WORK_STATE_IDLE = 0
	WORK_STATE_WORKING = 1

	def __init__(self, param):
		logging.debug("SnLocalManager.__init__: Start")

		# variables
		self.param = param
		self.localInfo = self._getLocalInfo()
		self.moduleObjDict = self._getModuleObjDict()
		self.sleepNotifier = SnSleepNotifier(self.onBeforeSleep, self.onAfterResume)

		# active local peers
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
				assert mo.getState() in [ SnModuleInstance.STATE_EXCEPT, SnModuleInstance.STATE_INACTIVE ]

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

	def getModuleKeyList(self):
		ret = []
		for pn, moduleObjList in self.moduleObjDict.items():
			for mo in moduleObjList:
				reti = (pn, mo.getUserName(), mo.getModuleName())
				ret.append(reti)
		return ret

	def getModuleState(self, peerName, userName, moduleName):
		mo = self._getModule(peerName, userName, moduleName)
		return (mo.getState(), mo.getFailMessage())

	##### event callback ####

	def onPeerChange(self, peerName, peerInfo):
		logging.debug("SnLocalManager.onPeerChange: Start, %s", peerName)

		# no peer module
		for mo in self.moduleObjDict[peerName]:
			# find module in peerInfo
			match = False
			for mio in peerInfo.moduleList:
				if mo.getUserName() == mio.userName and mo.getModuleName() == self._getMappedModuleName(mio.moduleName):
					match = True
					break
			if match:
				continue

			# found none
			if mo.getState() == SnModuleInstance.STATE_ACTIVE:
				logging.debug("SnLocalManager.onPeerChange: mo active -> inactive start, %s, %s, %s", peerName, mo.getUserName(), mo.getModuleName())
				try:
					mo.setState(SnModuleInstance.STATE_INACTIVE)
					SnUtil.euidInvoke(mo.getUserName(), mo.onInactive)
					shutil.rmtree(mo.getTmpDir2(), True)
					logging.debug("SnLocalManager.onPeerChange: mo active -> inactive end")
				except Exception as e:
					mo.setState(SnModuleInstance.STATE_EXCEPT, traceback.format_exc())
					logging.debug("SnLocalManager.onPeerChange: mo onInactive failed, %s, %s", e.__class__, e)
			elif mo.getState() == SnModuleInstance.STATE_INACTIVE:
				pass
			elif mo.getState() == SnModuleInstance.STATE_REJECT:
				logging.debug("SnLocalManager.onPeerChange: mo reject -> inactive start, %s, %s, %s", peerName, mo.getUserName(), mo.getModuleName())
				mo.setState(SnModuleInstance.STATE_INACTIVE)
				logging.debug("SnLocalManager.onPeerChange: mo reject -> inactive end")
			elif mo.getState() == SnModuleInstance.STATE_PEER_REJECT:
				logging.debug("SnLocalManager.onPeerChange: mo peer_reject -> inactive start, %s, %s, %s", peerName, mo.getUserName(), mo.getModuleName())
				mo.setState(SnModuleInstance.STATE_INACTIVE)
				logging.debug("SnLocalManager.onPeerChange: mo peer_reject -> inactive end")
			elif mo.getState() == SnModuleInstance.STATE_EXCEPT:
				pass
			elif mo.getState() == SnModuleInstance.STATE_PEER_EXCEPT:
				logging.debug("SnLocalManager.onPeerChange: mo peer_except -> inactive start, %s, %s, %s", peerName, mo.getUserName(), mo.getModuleName())
				mo.setState(SnModuleInstance.STATE_INACTIVE)
				logging.debug("SnLocalManager.onPeerChange: mo peer_except -> inactive end")
			else:
				assert False

		# has peer module
		for mio in peerInfo.moduleList:
			mo = self._findModuleMapped(peerName, mio.userName, mio.moduleName)
			if mo is None:
				continue

			# found module
			if mo.getState() == SnModuleInstance.STATE_ACTIVE:
				pass
			elif mo.getState() == SnModuleInstance.STATE_INACTIVE:
				logging.debug("SnLocalManager.onPeerChange: mo inactive -> active start, %s, %s, %s", peerName, mo.getUserName(), mo.getModuleName())
				try:
					mo.setState(SnModuleInstance.STATE_ACTIVE)
					SnUtil.euidInvoke(mo.getUserName(), mo.onActive)
					logging.debug("SnLocalManager.onPeerChange: mo inactive -> active end")
				except Exception as e:
					mo.setState(SnModuleInstance.STATE_EXCEPT, traceback.format_exc())
					self._sendExcept(peerName, mo.getUserName(), mo.getModuleName())
					logging.debug("SnLocalManager.onPeerChange: mo onActive failed, %s, %s", e.__class__, e)
			elif mo.getState() == SnModuleInstance.STATE_REJECT:
				pass
			elif mo.getState() == SnModuleInstance.STATE_PEER_REJECT:
				pass
			elif mo.getState() == SnModuleInstance.STATE_EXCEPT:
				pass
			elif mo.getState() == SnModuleInstance.STATE_PEER_EXCEPT:
				pass
			else:
				assert False

		logging.debug("SnLocalManager.onPeerChange: End")
		return

	def onPeerRemove(self, peerName):
		logging.debug("SnLocalManager.onPeerRemove: Start, %s", peerName)

		for mo in self.moduleObjDict[peerName]:
			if mo.getState() == SnModuleInstance.STATE_ACTIVE:
				logging.debug("SnLocalManager.onPeerRemove: mo active -> inactive start, %s, %s, %s", peerName, mo.getUserName(), mo.getModuleName())
				try:
					mo.setState(SnModuleInstance.STATE_INACTIVE)
					SnUtil.euidInvoke(mo.getUserName(), mo.onInactive)
					shutil.rmtree(mo.getTmpDir2(), True)
					logging.debug("SnLocalManager.onPeerRemove: mo active -> inactive end")
				except Exception as e:
					mo.setState(SnModuleInstance.STATE_EXCEPT, traceback.format_exc())
					logging.debug("SnLocalManager.onPeerChange: mo onInactive failed, %s, %s", e.__class__, e)
			elif mo.getState() == SnModuleInstance.STATE_INACTIVE:
				pass
			elif mo.getState() == SnModuleInstance.STATE_REJECT:
				logging.debug("SnLocalManager.onPeerRemove: mo reject -> inactive start, %s, %s, %s", peerName, mo.getUserName(), mo.getModuleName())
				mo.setState(SnModuleInstance.STATE_INACTIVE)
				logging.debug("SnLocalManager.onPeerRemove: mo reject -> inactive end")
			elif mo.getState() == SnModuleInstance.STATE_PEER_REJECT:
				logging.debug("SnLocalManager.onPeerRemove: mo peer_reject -> inactive start, %s, %s, %s", peerName, mo.getUserName(), mo.getModuleName())
				mo.setState(SnModuleInstance.STATE_INACTIVE)
				logging.debug("SnLocalManager.onPeerRemove: mo peer_reject -> inactive end")
			elif mo.getState() == SnModuleInstance.STATE_EXCEPT:
				pass
			elif mo.getState() == SnModuleInstance.STATE_PEER_EXCEPT:
				logging.debug("SnLocalManager.onPeerRemove: mo peer_except -> inactive start, %s, %s, %s", peerName, mo.getUserName(), mo.getModuleName())
				mo.setState(SnModuleInstance.STATE_INACTIVE)
				logging.debug("SnLocalManager.onPeerRemove: mo peer_except -> inactive end")
			else:
				assert False

		logging.debug("SnLocalManager.onPeerRemove: End")
		return

	def onPacketRecv(self, peerName, userName, srcModuleName, data):
		logging.debug("SnLocalManager.onPacketRecv: Start, %s, %s, %s", peerName, userName, srcModuleName)

		mo = self._getModuleMapped(peerName, userName, srcModuleName)
		assert mo.getState() == SnModuleInstance.STATE_ACTIVE

		if self._typeCheck(data, SnDataPacketReject):
			try:
				mo.setState(SnModuleInstance.STATE_PEER_REJECT, data.message)
				SnUtil.euidInvoke(mo.getUserName(), mo.onInactive)
				shutil.rmtree(mo.getTmpDir2(), True)
			except Exception as e:
				mo.setState(SnModuleInstance.STATE_EXCEPT, traceback.format_exc())
				logging.debug("SnLocalManager.onPacketRecv: mo onInactive failed, %s, %s", e.__class__, e)
		elif self._typeCheck(data, SnDataPacketExcept):
			try:
				mo.setState(SnModuleInstance.STATE_PEER_EXCEPT)
				SnUtil.euidInvoke(mo.getUserName(), mo.onInactive)
				shutil.rmtree(mo.getTmpDir2(), True)
			except Exception as e:
				mo.setState(SnModuleInstance.STATE_EXCEPT, traceback.format_exc())
				logging.debug("SnLocalManager.onPacketRecv: mo onInactive failed, %s, %s", e.__class__, e)
		else:
			try:
				SnUtil.euidInvoke(mo.getUserName(), mo.onRecv, data)
			except SnRejectException as e:
				self._toRejectWithMessage(peerName, mo, e.message)
				logging.debug("SnLocalManager.onPacketRecv: mo onRecv failed, %s, %s", e.__class__, e)
			except Exception as e:
				mo.setState(SnModuleInstance.STATE_EXCEPT, traceback.format_exc())
				self._sendExcept(peerName, mo.getUserName(), mo.getModuleName())
				logging.debug("SnLocalManager.onPacketRecv: mo onRecv failed, %s, %s", e.__class__, e)

		logging.debug("SnLocalManager.onPacketRecv: End")

	def onBeforeSleep(self, sleepType):
		pass

	def onAfterResume(self, sleepType):
		pass

	def onLoSockConnected(self, sock):
		pass

	def onLoSockRecv(self, sock, packetObj):
		if self._typeCheck(packetObj, _LoSockCall):
			assert False
		elif self._typeCheck(packetObj, _LoSockRetn):
			pass
		elif self._typeCheck(packetObj, _LoSockExcp):
			pass
		elif self._typeCheck(packetObj, _LoSockSendObj):
			self._sendObject(packetObj.peerName, packetObj.userName, packetObj.moduleName, packetObj.dataObj)
		else:
			assert False

	def onLoSockError(self, sock, errMsg):
		pass

	##### implementation ####

	def _sendObject(self, peerName, userName, moduleName, obj):
		if peerName == socket.gethostname():
			GLib.idle_add(self._idleLocalPeerRecv, peerName, userName, moduleName, obj)
		else:
			self.param.peerManager._sendDataObject(peerName, userName, moduleName, obj)

	def _toRejectWithMessage(self, peerName, mo, rejectMessage):
		try:
			mo.setState(SnModuleInstance.STATE_REJECT, rejectMessage)
			SnUtil.euidInvoke(mo.getUserName(), mo.onInactive)
			shutil.rmtree(mo.getTmpDir2(), True)
			self._sendReject(peerName, mo.getUserName(), mo.getModuleName(), rejectMessage)
		except Exception as e:
			mo.setState(SnModuleInstance.STATE_EXCEPT, traceback.format_exc())
			logging.debug("SnLocalManager._toReject: mo onInactive failed, %s, %s", e.__class__, e)
			self._sendExcept(peerName, mo.getUserName(), mo.getModuleName())

	def _sendReject(self, peerName, userName, moduleName, rejectMessage):
		logging.warning("send reject, %s, %s, %s, %s", peerName, userName, moduleName, rejectMessage)

		messageObj = SnDataPacketReject()
		messageObj.message = rejectMessage
		if peerName == socket.gethostname():
			GLib.idle_add(self._idleLocalPeerRecv, peerName, userName, moduleName, messageObj)
		else:
			self.param.peerManager._sendDataObject(peerName, userName, moduleName, messageObj)

	def _sendExcept(self, peerName, userName, moduleName):
		logging.warning("send except, %s, %s, %s", peerName, userName, moduleName)

		messageObj = SnDataPacketExcept()
		if peerName == socket.gethostname():
			GLib.idle_add(self._idleLocalPeerRecv, peerName, userName, moduleName, messageObj)
		else:
			self.param.peerManager._sendDataObject(peerName, userName, moduleName, messageObj)

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

				if pname == socket.gethostname() and not minfo.moduleObj.getPropDict()["allow-local-peer"]:
					continue

				exec("from %s import ModuleInstanceObject"%(mname.replace("-", "_")))
				if minfo.moduleScope == "sys":
					mo = ModuleInstanceObject(self, pname, None, mname,
							os.path.join(self.param.tmpDir, mname))
					logging.debug("SnLocalManager._getModuleObjDict: mo init, %s, %s", pname, mo.getModuleName())
					try:
						SnUtil.euidInvoke(mo.getUserName(), mo.onInit)
						mo.setState(SnModuleInstance.STATE_INACTIVE)
						logging.debug("SnLocalManager._getModuleObjDict: mo init end")
					except Exception as e:
						mo.setState(SnModuleInstance.STATE_EXCEPT, traceback.format_exc())
						logging.debug("SnLocalManager._getModuleObjDict: mo onInit failed, %s, %s", e.__class__, e)
					moduleObjList.append(mo)
				elif minfo.moduleScope == "usr":
					for uname in pgs.getNormalUserList():
						if uname in self.param.configManager.getUserBlackList():
							continue

						mo = ModuleInstanceObject(self, pname, uname, mname,
								os.path.join(self.param.tmpDir, "%s-%s"%(mname, uname)))
						logging.debug("SnLocalManager._getModuleObjDict: mo init, %s, %s, %s", pname, uname, mo.getModuleName())
						try:
							SnUtil.euidInvoke(mo.getUserName(), mo.onInit)
							mo.setState(SnModuleInstance.STATE_INACTIVE)
							logging.debug("SnLocalManager._getModuleObjDict: mo init end")
						except Exception as e:
							mo.setState(SnModuleInstance.STATE_EXCEPT, traceback.format_exc())
							logging.debug("SnLocalManager._getModuleObjDict: mo onInit failed, %s, %s", e.__class__, e)
						moduleObjList.append(mo)
				else:
					assert False
			ret[pname] = moduleObjList

		return ret

	def _getModule(self, peerName, userName, moduleName):
		for mo in self.moduleObjDict[peerName]:
			if mo.getUserName() == userName and mo.getModuleName() == moduleName:
				return mo
		assert False

	def _getModuleMapped(self, peerName, userName, srcModuleName):
		ret = self._findModuleMapped(peerName, userName, srcModuleName)
		assert ret is not None
		return ret

	def _findModuleMapped(self, peerName, userName, srcModuleName):
		for mo in self.moduleObjDict[peerName]:
			if mo.getUserName() == userName and mo.getModuleName() == self._getMappedModuleName(srcModuleName):
				return mo
		return None

	def _matchModuleMapped(self, peerName, userName, srcModuleName):
		ret = self._findModuleMapped(peerName, userName, srcModuleName)
		return ret is not None

	def _getMappedModuleName(self, moduleName):
		strList = moduleName.split("-")
		if strList[1] == "server":
			strList[1] = "client"
		elif strList[1] == "client":
			strList[1] = "server"
		return "-".join(strList)

	def _typeCheck(self, obj, typeobj):
		return str(obj.__class__) == str(typeobj)

class _ModuleInfoInternal:
	CALLING_NONE = 0
	CALLING_INIT = 1
	CALLING_ACTIVE = 2
	CALLING_INACTIVE = 3
	CALLING_REJECT = 4
	CALLING_RECV = 5

	minst = None							# obj, SnModuleInstance
	proc = None								# obj, None means not-standalone module
	callingState = None						# enum

class _LoSockCall:
	funcName = None							# str
	funcArgs = None							# list<obj>

class _LoSockRetn:
	retVal = None							# obj, None means no return value

class _LoSockExcp:
	excObj = None							# str
	excInfo = None							# str

class _LoSockSendObj:
	peerName = None							# str
	userName = None							# str
	moduleName = None						# str
	dataObj = None							# obj

