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
from sn_manager_local import _LoSockCall
from sn_manager_local import _LoSockRetn
from sn_manager_local import _LoSockExcp
from sn_manager_local import _LoSockSendObj

class SnSubProcess:

	def __init__(self, peerName, userName, moduleName, tmpDir, stopFunc):
		self.peerName = peerName
		self.userName = userName
		self.moduleName = moduleName
		self.tmpDir = tmpDir
		self.stopFunc = stopFunc
		self.pipeConn = None

	def start(self):
		self.pipeConn, child_conn = multiprocessing.Pipe()
		pargs = (self.peerName, self.userName, self.moduleName, self.tmpDir, child_conn,)
		multiprocessing.Process(target=_subproc_main, args=pargs)

	def stop(self):
		pass

	def get_pipe(self):
		return self.parent_conn

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

		# create module object, init module object
		exec("from %s import ModuleInstanceObject"%(self.moduleName.replace("-", "_")))
		self.mo = ModuleInstanceObject(self, self.peerName, self.userName, self.moduleName, self.tmpDir)
		try:
			self.mo.onInit()
		except Exception as e:
			self.mo.setState(SnModuleInstance.STATE_EXCEPT, traceback.format_exc())

	def onConnRecv(self, sock, packetObj):
		assert sock == self.connSock
		assert self._typeCheck(packetObj, _LoSockCall)
		
		if packetObj.funcName == "onActive":
			assert len(packetObj.funcArgs) == 0
			self.mo.onActive()
		elif packetObj.funcName == "onInactive":
			assert len(packetObj.funcArgs) == 0
			self.mo.onInactive()
		elif packetObj.funcName == "onRecv":
			assert len(packetObj.funcArgs) == 1
			self.mo.onRecv(packetObj.funcArgs[0])
		else:
			assert False

	def onConnError(self):
		assert False

	def _gcComplete(self):
		assert False

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

