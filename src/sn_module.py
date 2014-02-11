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

class SnModule:

	def getModuleName(self):
		assert False			# implement by subclass

	def getPropDict(self):
		"""Property list: allow-local-peer: true | false"""
		assert False			# implement by subclass

class SnModuleInstance:

	STATE_INACTIVE = 0
	STATE_ACTIVE = 1
	STATE_REJECT = 2
	
	##### hidden to subclass ####

	def __init__(self, coreProxy, classObj, paramDict, peerName, userName):
		self.core = coreProxy
		self.classObj = classObj			# SnModule
		self.paramDict = paramDict
		self.peerName = peerName
		self.userName = userName
		self.state = self.STATE_INACTIVE

	##### provide to subclass ####

	def getParamDict(self):
		return self.paramDict

	def getPeerName(self):
		return self.peerName

	def getUserName(self):
		return self.userName

	def getModuleName(self):
		return self.classObj.getModuleName()

	def send(self, data):
		self.core._sendToPeer(self.getPeerName(), data)

	def reject(self, rejectMessage):
		self.core._rejectPeer(self.getPeerName(), rejectMessage)

	##### provide to core only ####

	def getState(self):
		return self.state

	def setState(self, state):
		self.state = state

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

class SnModuleException(Exception):
	pass

class _SnModuleCoreProxy:

	def getHostName(self):
		assert False

	def getNetRange(self):
		"""Get the network range of selfnet, format: 192.168.1.1/255.255.255.0 or 128::1/24"""
		assert False

	def _sendToPeer(self, peerName, data):
		pass

	def _rejectPeer(self, peerName, rejectMessage):
		pass

