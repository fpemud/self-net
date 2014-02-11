#!/usr/bin/python2
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

from sn_module import SnModule
from sn_module import SnModuleInstance

class ModuleObject(SnModule):

	def getModuleName(self):
		return "sys-client-distcc"

	def getPropDict(self):
		ret = dict()
		ret["allow-local-peer"] = True
		return ret

class ModuleInstanceObject(SnModuleInstance):

	def onInit(self):
		return

	def onActive(self):
		return

	def onInactive(self):
#		if self.getPeerName() == self.core.getHostName():
#			return

		# remove peer from distcc configuration file
		cfgFile = ConfigFile("/etc/distcc/hosts")
		cfgFile.removeHost(self.getPeerName())

	def onReject(self, rejectMessage):
		return

	def onRecv(self, dataObj):
#		if self.getPeerName() == self.core.getHostName():
#			return

		if not isinstance(obj, MachineParam):
			self.sendReject("invalid data received")
			return

		# add peer to distcc configuration file
		cfgFile = ConfigFile("/etc/distcc/hosts")
		cfgFile.addHost(ConfigFile.Host(self.getPeerName(), dataObj.jobNumber))

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

	def addHost(self, hostObj):
		assert isinstance(hostObj, ConfigFile.Host)
		self._open()
		self.hostList.append(hostObj)
		self._close()

	def removeHost(self, hostName):
		self._open()
		newList = []
		for i in self.hostList:
			if i.name == hostName:
				continue
			newList.append(i)
		self.hostList = newList
		self._close()

	def _open(self):
		self.hostList = []

		f = open(self.filename, 'r')
		buf = f.read()
		f.close()

		hostStrList = buf.split()
		for i in hostStrList:
			parts = i.split("/")
			if len(parts) == 2:
				self.hostList.append(ConfigFile.Host(parts[0], parts[1]))

	def _close(self):
		buf = ""
		for i in self.hostList:
			buf += "%s/%d "%(i.name, i.jobNumber)

		f = open(self.filename, 'w')
		f.write(buf)
		f.close()

