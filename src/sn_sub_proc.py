#!/usr/bin/python2
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import os
import traceback
import multiprocessing
from objsocket import objsocket
from gi.repository import GLib

from sn_util import SnUtil
from sn_param import SnParam
from sn_module import SnRejectException

class LocalSockSendObj:
	dataObj = None							# obj

class LocalSockSetWorkState:
	workState = None						# enum

class LocalSockCall:
	funcName = None							# str
	funcArgs = None							# list<obj>

class LocalSockRetn:
	retVal = None							# obj, None means no return value

class LocalSockExcp:
	excObj = None							# str
	excInfo = None							# str

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
		self.pipeConn = objsocket(parent_conn, self.onConnRecv, self._onConnError, self._gcComplete)
		pargs = (self.peerName, self.userName, self.moduleName, self.tmpDir, child_conn,)
		multiprocessing.Process(target=_subproc_main, args=pargs)

	def get_pipe(self):
		return self.pipeConn

	def onConnRecv(self, sock, packetObj):
		assert sock == self.pipeConn
		self.recvFunc(self, self.peerName, self.userName, self.moduleName, packetObj)

	def _onConnError(self, sock, errMsg):
		assert sock == self.pipeConn
		sock.close()
		self.stopFunc(self)

	def _gcComplete(self, sock):
		assert sock == self.pipeConn
		assert False

def _subproc_main(peerName, userName, moduleName, tmpDir, pipeConn):
	# drop priviledge
	if userName is not None:
		SnUtil.dropPriviledgeTo(userName)

	mainloop = GLib.MainLoop()
	_SubprocObject(mainloop, peerName, userName, moduleName, tmpDir, pipeConn)
	mainloop.run()

class _SubprocObject:

	def __init__(self, mainloop, peerName, userName, moduleName, tmpDir, pipeConn):
		self.mainloop = mainloop
		self.peerName = peerName
		self.userName = userName
		self.moduleName = moduleName
		self.tmpDir = tmpDir
		self.connSock = objsocket(pipeConn, self.onConnRecv, self._onConnError, self._gcComplete)
		self.mo = None

		# create module object
		exec("from %s import ModuleInstanceObject"%(self.moduleName.replace("-", "_")))
		self.mo = ModuleInstanceObject(self, self.peerName, self.userName, self.moduleName, self.tmpDir)

	def onConnRecv(self, sock, packetObj):
		assert sock == self.connSock
		assert _typeCheck(packetObj, LocalSockCall)

		if packetObj.funcName == "onActive":
			assert len(packetObj.funcArgs) == 0
			try:
				self.mo.onInit()
				self.mo.onActive()
				self._sendRetn(None)
			except Exception as e:
				self._sendExcp(e, traceback.format_exc())
				self.mainloop.quit()
		elif packetObj.funcName == "onRecv":
			assert len(packetObj.funcArgs) == 1
			try:
				self.mo.onRecv(packetObj.funcArgs[0])
				self._sendRetn(None)
			except SnRejectException as e:
				self._sendExcp(e, None)			# no traceback needed for reject exception
			except Exception as e:
				self._sendExcp(e, traceback.format_exc())
				self.mainloop.quit()
		elif packetObj.funcName == "onInactive":
			assert len(packetObj.funcArgs) == 0
			try:
				self.mo.onInactive()
				self._sendRetn(None)
				self.mainloop.quit()
			except Exception as e:
				self._sendExcp(e, traceback.format_exc())
				self.mainloop.quit()
		else:
			assert False

	def _onConnError(self, sock):
		assert False

	def _gcComplete(self, sock):
		assert False

	def _sendRetn(self, retVal):
		packetObj = LocalSockRetn()
		packetObj.retVal = retVal
		self.connSock.send(packetObj)

	def _sendExcp(self, excObj, excInfo):
		packetObj = LocalSockExcp()
		packetObj.excObj = excObj
		packetObj.excInfo = excInfo
		self.connSock.send(packetObj)

	def _sendObject(self, peerName, userName, moduleName, obj):
		packetObj = LocalSockSendObj()
		packetObj.dataObj = obj
		self.connSock.send(packetObj)

	def _setWorkState(self, peerName, userName, moduleName, workState):
		packetObj = LocalSockSetWorkState()
		packetObj.workState = workState
		self.connSock.send(packetObj)

_flagError = GLib.IO_PRI | GLib.IO_ERR | GLib.IO_HUP | GLib.IO_NVAL

def _typeCheck(obj, typeobj):
	return str(obj.__class__) == str(typeobj)

