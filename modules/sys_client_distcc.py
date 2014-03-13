#!/usr/bin/python2
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import os
from sn_util import SnUtil
from sn_module import SnModule
from sn_module import SnModuleInstance
from sn_module import SnRejectException

class ModuleObject(SnModule):

	def getModuleName(self):
		return "sys-client-distcc"

	def getPropDict(self):
		ret = dict()
		ret["allow-local-peer"] = False
		ret["suid"] = False
		ret["standalone"] = False
		return ret

class ModuleInstanceObject(SnModuleInstance):

	def onInit(self):
		self.cfgDir = "/etc/distcc"
		self.hostsFile = os.path.join(self.cfgDir, "hosts")

		# check distcc config
		if not os.path.isdir(self.cfgDir):
			raise Exception("distcc configuration directory does not exist")

		# initialize distcc hosts file
		if not os.path.exists(self.hostsFile):
			SnUtil.touchFile(self.hostsFile)
		self._cleanup()

	def onActive(self):
		return

	def onInactive(self):
		self._cleanup()

	def onRecv(self, dataObj):
		if dataObj.__class__.__name__ == "_DistccServerObject":
			# add peer to distcc configuration file
			cfgFile = ConfigFile(self.hostsFile)
			cfgFile.addHost(ConfigFile.Host(self.getPeerName(), dataObj.jobNumber))
		else:
			raise SnRejectException("invalid data received")

	def _cleanup(self):
		cfgFile = ConfigFile(self.hostsFile)
		cfgFile.removeHost(self.getPeerName())

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

