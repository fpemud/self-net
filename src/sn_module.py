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

  STATE_INIT is the initial state.

  STATE_INIT        -> STATE_INACTIVE    : initialized
  STATE_INACTIVE    -> STATE_ACTIVE      : peer added, peer module added
  STATE_ACTIVE      -> STATE_INACTIVE    : peer removed, peer module removed

  STATE_ACTIVE      -> STATE_REJECT      : onRecv raise SnRejectException
  STATE_ACTIVE      -> STATE_PEER_REJECT : reject received
  STATE_REJECT      -> STATE_INACTIVE    : peer removed, peer module removed
  STATE_PEER_REJECT -> STATE_INACTIVE    : peer removed, peer module removed

  STATE_INIT        -> STATE_EXCEPT      : onInit raise exception
  STATE_INACTIVE    -> STATE_EXCEPT      : onActive raise exception
  STATE_ACTIVE      -> STATE_EXCEPT      : onRecv / onInactive raise exception
  STATE_ACTIVE      -> STATE_PEER_EXCEPT : except received
  STATE_PEER_EXCEPT -> STATE_INACTIVE    : peer removed, peer module removed
"""

"""
ModuleInstance FSM event callback table:

  STATE_INIT     -> STATE_INACTIVE    : call onInit        BEFORE state change
  STATE_INACTIVE -> STATE_ACTIVE      : call onActive      AFTER state change
  STATE_ACTIVE   -> STATE_INACTIVE    : call onInactive    AFTER state change
  STATE_ACTIVE   -> STATE_REJECT      : call onInactive    AFTER state change
  STATE_ACTIVE   -> STATE_PEER_REJECT : call onInactive    AFTER state change
  STATE_ACTIVE   -> STATE_EXCEPT      : call onInactive    AFTER state change
  STATE_ACTIVE   -> STATE_PEER_EXCEPT : call onInactive    AFTER state change

The concept is: module has no way to control the state change, it can only respond to it.
"""

import os
import socket

class SnModule:

	def getModuleName(self):
		assert False			# implement by subclass

	def getPropDict(self):
		"""Property list: allow-local-peer: true | false
		                  suid: true | false"""
		assert False			# implement by subclass

class SnModuleInstance:

	STATE_INIT = 0
	STATE_INACTIVE = 1
	STATE_ACTIVE = 2
	STATE_REJECT = 3
	STATE_PEER_REJECT = 4
	STATE_EXCEPT = 5
	STATE_PEER_EXCEPT = 6

	WORK_STATE_IDLE = 0
	WORK_STATE_WORKING = 1
	
	##### hidden to subclass ####

	def __init__(self, coreObj, peerName, userName, moduleName, tmpDir):
		self.coreObj = coreObj
		self.peerName = peerName
		self.userName = userName
		self.moduleName = moduleName
		self.tmpDir = tmpDir

		self.state = self.STATE_INIT
		self.workState = self.WORK_STATE_IDLE
		self.failMessage = ""					# reject / except message

	##### provide to subclass ####

	def getHostName(self):
		return socket.gethostname()

	def getPeerName(self):
		return self.peerName

	def getUserName(self):
		return self.userName

	def getModuleName(self):
		return self.moduleName

	def isLocalPeer(self):
		return self.peerName == socket.gethostname()

	def getTmpDir(self):
		"""Temp directory is created when being used for the first time, deleted
		   before change to inactive state"""

		if not os.path.exists(self.tmpDir):
			os.mkdir(self.tmpDir)
		return self.tmpDir

	def sendObject(self, obj):
		self.coreObj._sendObject(self.peerName, self.userName, self.moduleName, obj)

	def setWorkState(self, workState):
		self.workState = workState

	##### provide to coreObj only ####

	def getTmpDir2(self):
		return self.tmpDir

	def getState(self):
		return self.state

	def setState(self, state, failMessage=""):
		if state in [ self.STATE_REJECT, self.STATE_PEER_REJECT, self.STATE_EXCEPT ]:
			assert failMessage != ""
		else:
			assert failMessage == ""
		self.state = state
		self.failMessage = failMessage

	def getFailMessage(self):
		return self.failMessage

	def getWorkState(self):
		return self.workState

	def onInit(self):
		"""Called after the module instance object is created"""
		assert False			# implement by subclass

	def onActive(self):
		"""Called after the peer changes to active state"""
		assert False			# implement by subclass

	def onInactive(self):
		"""Called before the peer changes to inactive state"""
		assert False			# implement by subclass

	def onRecv(self, dataObj):
		"""Called when data is received from the peer"""
		assert False			# implement by subclass

class SnRejectException(Exception):
	pass

