#!/usr/bin/python2
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

class SnModule:

	##### hidden to subclass ####

	def __init__(self, coreProxy, peerName, userName, moduleName):
		self.core = coreProxy
		self.peerName = peerName
		self.userName = userName
		self.moduleName = moduleName

	##### called by subclass ####

	def getConfig(self):
		"""Get the configuration"""
		assert False

	def getPeerName(self):
		return self.peerName

	def getUserName(self):
		return self.userName

	def getModuleName(self):
		return self.moduleName

	def send(self, data):
		self.core._sendToPeer(self.getPeerName(), data)

	def reject(self, rejectMessage):
		self.core._rejectPeer(self.getPeerName(), rejectMessage)

	##### implement by subclass ####

	def onActive(self):
		"""Called after the peer changes to active state"""
		assert False

	def onInactive(self):
		"""Called before the peer changes to inactive state"""
		assert False

	def onReject(self, rejectMessage):
		"""Called when rejection is received from the peer, peer state changes to inactive after this method call"""
		assert False

	def onRecv(self, dataObj):
		"""Called when data is received from the peer"""
		assert False

class SnModuleCoreProxy:

	def getHostName(self):
		assert False

	def getNetRange(self):
		"""Get the network range of selfnet, format: 192.168.1.1/255.255.255.0 or 128::1/24"""
		assert False

	def _sendToPeer(self, peerName, data):
		pass

	def _rejectPeer(self, peerName, rejectMessage):
		pass

