#!/usr/bin/python2
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

from sn_module import SnModule

class ModuleObject(SnModule):

	def getModuleName(self):
		return "usr-client-ssh"

	def getProperty(self, propertyName):
		if propertyName == "allow-local-peer":
			return True
		return None

class ModuleInstanceObject(SnModuleInstance):

	def onActive(self):
		# send sys param to client
		obj = ModuleDistccServerMachineParam()
		obj.jobNumber = 4
		self.send(obj)

	def onInactive(self):
		"""ignore this event"""
		return

	def onRecv(self, dataObj):
		self.reject("receive client data")


