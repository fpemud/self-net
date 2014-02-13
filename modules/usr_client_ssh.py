#!/usr/bin/python2
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import os
from sn_util import SnUtil
from sn_module import SnModule
from sn_module import SnModuleInstance

class ModuleObject(SnModule):

	def getModuleName(self):
		return "usr-client-ssh"

	def getPropDict(self):
		ret = dict()
		ret["allow-local-peer"] = True
		return ret

class ModuleInstanceObject(SnModuleInstance):

	def onInit(self):
		self.sshDir = os.path.expanduser("~%s/.ssh"%(self.getUserName()))
		self.privkeyFile = os.path.join(self.sshDir, "id_rsa")
		self.pubkeyFile = os.path.join(self.sshDir, "id_rsa.pub")

		# initialize config files
		if not os.path.exists(self.privkeyFile) or not os.path.exists(self.pubkeyFile):
			comment = "%s@%s"%(self.getUserName(), self.getHostName())
			SnUtil.forceDelete(self.privkeyFile)
			SnUtil.forceDelete(self.pubkeyFile)
			SnUtil.mkDir(self.sshDir)
			SnUtil.shell("/bin/ssh-keygen -N \"\" -C \"%s\" -f \"%s\" -q"%(comment, self.privkeyFile), "stdout")
			assert os.path.exists(self.privkeyFile) and os.path.exists(self.pubkeyFile)

	def onActive(self):
		obj = _SshClientObject()
		with open(self.pubkeyFile, "rt") as f:
			obj.pubkey = f.read()
		self.sendObject(obj)

	def onInactive(self):
		return

	def onReject(self, rejectMessage):
		return

	def onRecv(self, dataObj):
		self.sendReject("receive server data")

class _SshClientObject:
	pubkey = None				# str

