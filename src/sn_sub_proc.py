#!/usr/bin/python2
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import os
import sys
import logging
import traceback
import multiprocessing
from gi.repository import GLib

sys.path.append('/usr/lib/selfnetd')
sys.path.append('/usr/lib/selfnetd/modules')		# fixme
from objsocket import objsocket
from sn_util import SnUtil
from sn_param import SnParam
from sn_module import SnRejectException
from sn_manager_local import _LoSockSendObj
from sn_manager_local import _LoSockCall
from sn_manager_local import _LoSockRetn
from sn_manager_local import _LoSockExcp

class SnSubProcess:

	def __init__(self, peerName, userName, moduleName, tmpDir, recvFunc, stopFunc):
		self.peerName = peerName
		self.userName = userName
		self.moduleName = moduleName
		self.tmpDir = tmpDir
		self.recvFunc = recvFunc
		self.stopFunc = stopFunc
		self.pipeConn = None

	def start(self):
		parent_conn, child_conn = multiprocessing.Pipe()
		self.pipeConn = objsocket(parent_conn, self.onConnRecv, self.onConnError, self._gcComplete)
		pargs = (self.peerName, self.userName, self.moduleName, self.tmpDir, child_conn,)
		multiprocessing.Process(target=_subproc_main, args=pargs)

	def stop(self):
		pass

	def get_pipe(self):
		return self.pipeConn

	def onConnRecv(self, sock, packetObj):
		assert sock == self.pipeConn
		self.recvFunc(self, self.peerName, self.userName, self.moduleName, packetObj):

	def onConnError(self, sock, errMsg):
		assert sock == self.pipeConn
		assert False

	def _gcComplete(self, sock):
		assert sock == self.pipeConn
		assert False

def _subproc_main(peerName, userName, moduleName, pipeConn):
	# drop priviledge
	if userName is not None:
		SnUtil.dropPriviledgeTo(userName)

	mlobj = GLib.MainLoop()
	_SubprocObject(peerName, userName, moduleName, pipeConn)
	mlobj.run()

class _SubprocObject:

	def __init__(self, peerName, userName, moduleName, pipeConn, tmpDir):
		self.peerName = peerName
		self.userName = userName
		self.moduleName = moduleName
		self.tmpDir = tmpDir
		self.connSock = objsocket(pipeConn, self.onConnRecv, self.onConnError, self._gcComplete)
		self.mo = None

		# create module object
		exec("from %s import ModuleInstanceObject"%(self.moduleName.replace("-", "_")))
		self.mo = ModuleInstanceObject(self, self.peerName, self.userName, self.moduleName, self.tmpDir)

	def onConnRecv(self, sock, packetObj):
		assert sock == self.connSock
		assert self._typeCheck(packetObj, _LoSockCall)

		if packetObj.funcName in [ "onInit", "onActive", "onInactive" ]:
			assert len(packetObj.funcArgs) == 0
			try:
				exec("self.mo.%s()"%(packetObj.funcName))
				self._sendRetn(None)
			except Exception as e:
				self._sendExcp(e, traceback.format_exc())
		elif packetObj.funcName == "onRecv":
			assert len(packetObj.funcArgs) == 1
			try:
				self.mo.onRecv(packetObj.funcArgs[0])
				self._sendRetn(None)
			except SnRejectException as e:
				self._sendExcp(e, None)			# no traceback needed for reject exception
			except Exception as e:
				self._sendExcp(e, traceback.format_exc())
		else:
			assert False

	def onConnError(self):
		assert False

	def _gcComplete(self):
		assert False

	def _sendRetn(self, retVal):
		packetObj = _LoSockRetn()
		packetObj.retVal = retVal
		self.connSock.send(packetObj)

	def _sendExcp(self, excObj, excInfo):
		packetObj = _LoSockExcp()
		packetObj.excObj = excObj
		packetObj.excInfo = excInfo
		self.connSock.send(packetObj)

	def _sendObject(self, peerName, userName, moduleName, obj):
		packetObj = _LoSockSendObj()
		packetObj.peerName = peerName
		packetObj.userName = userName
		packetObj.moduleName = moduleName
		packatObj.dataObj = obj
		self.connSock.send(packetObj)

	def _typeCheck(self, obj, typeobj):
		return str(obj.__class__) == str(typeobj)

_flagError = GLib.IO_PRI | GLib.IO_ERR | GLib.IO_HUP | GLib.IO_NVAL

