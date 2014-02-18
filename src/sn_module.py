#!/usr/bin/python2
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

"""
Selfnet module name consists of 3 parts: scope, type, id, separated by "-".
Some example: sys-server-distcc, sys-client-distcc, usr-server-ssh, usr-client-ssh
"scope" can have 2 values: sys and usr.
"type" can have 3 values: server, client, peer.
"id" is a string with maximum length of 32 characters, for which valid charater is [A-Za-z0-9_].

Replace "-" with "_" can selfnet module name be converted to python module name.
"""

"""
ModuleInstance FSM trigger table:

  STATE_NONE is the initial state.

  STATE_NONE     -> STATE_INIT_FAILED : initializing failed
  STATE_NONE     -> STATE_INACTIVE    : initialized
  STATE_INACTIVE -> STATE_ACTIVE      : peer added, peer module added
  STATE_ACTIVE   -> STATE_INACTIVE    : peer removed, peer module removed
  STATE_ACTIVE   -> STATE_REJECT      : reject sent, reject received
  STATE_REJECT   -> STATE_INACTIVE    : peer removed, peer module removed
"""

"""
ModuleInstance FSM callback table:

  STATE_NONE     -> STATE_INACTIVE    : call onInit
  STATE_INACTIVE -> STATE_ACTIVE      : call onActive
  STATE_ACTIVE   -> STATE_INACTIVE    : call onInactive
  STATE_ACTIVE   -> STATE_REJECT      : call onInactive
  STATE_ACTIVE                        : call onRecv when data received
  STATE_ACTIVE                        : call onReject when reject received
"""

import socket

class SnModule:

	def getModuleName(self):
		assert False			# implement by subclass

	def getPropDict(self):
		"""Property list: allow-local-peer: true | false
		                  suid: true | false"""
		assert False			# implement by subclass

class SnModuleInstance:

	STATE_NONE = 0
	STATE_INIT_FAILED = 1
	STATE_INACTIVE = 2
	STATE_ACTIVE = 3
	STATE_REJECT = 4

	WORK_STATE_IDLE = 0
	WORK_STATE_WORKING = 1
	
	##### hidden to subclass ####

	def __init__(self, initParam):
		self.initParam = initParam

		self.coreObj = initParam.coreObj		# for convience
		self.classObj = initParam.classObj
		self.paramDict = initParam.paramDict
		self.peerName = initParam.peerName
		self.userName = initParam.userName
		self.tmpDir = initParam.tmpDir

		self.state = self.STATE_NONE
		self.workState = self.WORK_STATE_IDLE
		self.initFailMessage = ""

	##### provide to subclass ####

	def getParamDict(self):
		return self.paramDict

	def getHostName(self):
		return socket.gethostname()

	def getPeerName(self):
		return self.peerName

	def getUserName(self):
		return self.userName

	def getModuleName(self):
		return self.classObj.getModuleName()

	def getTmpDir(self):
		"""Temp directory is created when being used for the first time, deleted
		   before change to inactive state"""

		if not os.path.exists(self.tmpDir):
			os.mkdir(self.tmpDir)
		return self.tmpDir

	def sendObject(self, obj):
		self.coreObj._sendObject(self.peerName, self.userName, self.classObj.getModuleName(), obj)

	def sendReject(self, rejectMessage):
		self.coreObj._sendReject(self.peerName, self.userName, self.classObj.getModuleName(), rejectMessage)

	def setWorkState(self, workState):
		self.workState = workState

	##### provide to coreObj only ####

	def getInitParam(self):
		return self.initParam

	def getState(self):
		return self.state

	def setState(self, state):
		self.state = state

	def getWorkState(self):
		return self.workState

	def getInitFailMessage(self):
		return self.initFailMessage

	def setInitFailMessage(self, initFailMessage):
		self.initFailMessage = initFailMessage

	def onInit(self):
		"""Called after the module instance object is created"""
		assert False			# implement by subclass

	def onActive(self):
		"""Called after the peer changes to active state"""
		assert False			# implement by subclass

	def onInactive(self):
		"""Called before the peer changes to inactive state"""
		assert False			# implement by subclass

	def onReject(self, rejectMessage):
		"""Called when rejection is received from the peer"""
		assert False			# implement by subclass

	def onRecv(self, dataObj):
		"""Called when data is received from the peer"""
		assert False			# implement by subclass

class SnModuleInstanceInitParam:
	coreObj = None		# obj, SnLocalManager
	classObj = None		# obj, SnModule
	paramDict = None	# dict
	peerName = None		# str
	userName = None		# str
	tmpDir = None		# str

class SnModuleInstanceInitException(Exception):
	pass

