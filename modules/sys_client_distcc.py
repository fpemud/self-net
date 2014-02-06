#!/usr/bin/python2
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

from sn_module import SnModule
from sn_module import SnModuleInstance

class ModuleObject(SnModule):

	def getModuleName(self):
		return "sys-client-distcc"

	def getProperty(self, propertyName):
		if propertyName == "allow-local-peer":
			return True
		return None

class ModuleInstanceObject(SnModuleInstance):

	def onInit(self):
		return

	def onActive(self):
		"""ignore this event"""
		return

	def onInactive(self):
		if self.getPeerName() == self.core.getHostName():
			return

		# remove peer from distcc configuration file
		self.removePeer(self.getPeerName())

	def onReject(self, rejectMessage):
		if self.getPeerName() == self.core.getHostName():
			return

		# remove peer from distcc configuration file
		self.removePeer(self.getPeerName())

	def onRecv(self, dataObj):
		if self.getPeerName() == self.core.getHostName():
			return

		if not isinstance(obj, MachineParam):
			self.reject("invalid data received")
			return

		# add peer to distcc configuration file
		self._addPeer(self.getPeerName(), dataObj.jobNumber)

	def _addPeer(self, peerName, jobNumber):
		cfgFile = ConfigFile("/etc/distcc/hosts")
		cfgFile.load()
		cfgFile.addHost(ConfigFile.Host(self.getPeerName(), dataObj.jobNumber))
		cfgFile.save()

	def _removePeer(self, peerName):
		cfgFile = ConfigFile("/etc/distcc/hosts")
		cfgFile.load()
		cfgFile.removeHost(peerName)
		cfgFile.save()

class MachineParam:
	jobNumber = None				# int

class ConfigFile:

	class Host:
		def __init__(self, name, jobNumber):
			self.name = name
			self.jobNumber = jobNumber

	def __init__(self, filename):
		self.filename = filename
		self.hostList = []

	def load(self):
		self.hostList = []

		f = open(self.filename, 'r')
		buf = f.read()
		f.close()

		hostStrList = buf.split()
		for i in hostStrList:
			parts = i.split("/")
			if len(parts) == 2:
				self.hostList.append(ConfigFile.Host(parts[0], parts[1]))

	def save(self):
		buf = ""
		for i in self.hostList:
			buf += "%s/%d "%(i.name, i.jobNumber)

		f = open(self.filename, 'w')
		f.write(buf)
		f.close()

	def addHost(self, hostObj):
		assert isinstance(hostObj, ConfigFile.Host)
		self.hostList.append(hostObj)

	def removeHost(self, hostName):
		newList = []
		for i in self.hostList:
			if i.name == hostName:
				continue
			newList.append(i)
		self.hostList = newList

