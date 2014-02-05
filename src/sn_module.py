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

	def getProperty(self, propertyName):
		"""Property list:
		     allow-local-peer: true | false
		   Returns None for unknown property name"""
		assert False			# implement by subclass

class SnModuleInstance:

	##### hidden to subclass ####

	def __init__(self, coreProxy, classObj, peerName, userName):
		self.core = coreProxy
		self.classObj = classObj			# SnModule
		self.peerName = peerName
		self.userName = userName

	##### provide to subclass ####

	def getConfig(self):
		"""Get the configuration"""
		assert False			# fixme

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

	def onActive(self):
		"""Called after the peer changes to active state"""
		assert False			# implement by subclass

	def onInactive(self):
		"""Called before the peer changes to inactive state"""
		assert False			# implement by subclass

	def onReject(self, rejectMessage):
		"""Called when rejection is received from the peer, peer state changes to inactive after this method call"""
		assert False			# implement by subclass

	def onRecv(self, dataObj):
		"""Called when data is received from the peer"""
		assert False			# implement by subclass

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

