#!/usr/bin/python2
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

from sn_module import SnModule
from sn_module import SnModuleInstance

class ModuleObject(SnModule):

	def getModuleName(self):
		return "sys-server-distcc"

	def getPropDict(self):
		ret = dict()
		ret["allow-local-peer"] = True
		return ret

class ModuleInstanceObject(SnModuleInstance):

	def onInit(self):
		return

	def onActive(self):
		# send sys param to client
		obj = _DistccServerObject()
		obj.jobNumber = 4
		self.sendObject(obj)

	def onInactive(self):
		return

	def onReject(self, rejectMessage):
		return

	def onRecv(self, dataObj):
		self.sendReject("receive client data")


class _DistccServerObject:
	jobNumber = None				# int

