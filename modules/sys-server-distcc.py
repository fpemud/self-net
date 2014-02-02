#!/usr/bin/python2
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

from sn_plugin import SnModule

class ModuleObject(SnModule):

	def onActive(self):
		# send sys param to client
		obj = MachineParam()
		obj.jobNumber = 4
		self.send(obj)

	def onInactive(self):
		"""ignore this event"""
		return

	def onReject(self, rejectMessage):
		"""ignore this event"""
		return

	def onRecv(self, dataObj):
		self.reject("receive client data")

class MachineParam:
	jobNumber = None				# int


