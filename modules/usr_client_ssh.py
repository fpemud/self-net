#!/usr/bin/python2
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import os
from sn_util import SnUtil
from sn_module import SnModule
from sn_module import SnModuleInstance

class ModuleObject(SnModule):

	def getModuleName(self):
		return "usr-client-ssh"

	def getProperty(self, propertyName):
		if propertyName == "allow-local-peer":
			return True
		return None

	def onInit(self):
		return

class ModuleInstanceObject(SnModuleInstance):

	def onInit(self):
		self.sshDir = os.path.expanduser("~%s/.ssh"%(self.getUserName()))
		self.privkeyFile = os.path.join(self.sshDir, "id_rsa")
		self.pubkeyFile = os.path.join(self.sshDir, "id_rsa.pub")

		# initialize config files
		if not os.path.exists(self.privkeyFile) or not os.path.exists(self.pubkeyFile):
			SnUtil.forceDelete(self.privkeyFile)
			SnUtil.forceDelete(self.pubkeyFile)
			SnUtil.mkDir(self.sshDir)
			SnUtil.shell("/bin/ssh-keygen -N \"\" -f %s -q"%(self.privkeyFile), "stdout")
			assert os.path.exists(self.privkeyFile) and os.path.exists(self.pubkeyFile)

	def onActive(self):
		obj = ModuleSshClientObject()
		with open(self.pubkeyFile, "rt") as f:
			obj.pubkey = f.read()
		self.send(obj)

	def onInactive(self):
		return

	def onReject(self, rejectMessage):
		return

	def onRecv(self, dataObj):
		self.reject("receive server data")

class _SshClientObject:
	pubkey = None				# str

