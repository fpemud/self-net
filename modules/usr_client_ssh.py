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
		ret["suid"] = False
		return ret

class ModuleInstanceObject(SnModuleInstance):

	def onInit(self):
		self.sshDir = os.path.expanduser("~%s/.ssh"%(self.getUserName()))
		self.privkeyFile = os.path.join(self.sshDir, "id_rsa")
		self.pubkeyFile = os.path.join(self.sshDir, "id_rsa.pub")
		self.knownHostsFile = os.path.join(self.sshDir, "known_hosts")

		# initialize user key file, known-hosts file
		SnUtil.mkDir(self.sshDir)
		SnUtil.initSshKeyFile("rsa", self.getUserName(), self.getHostName(), self.privkeyFile, self.pubkeyFile)
		_CfgFileKnownHosts(self.knownHostsFile).touch()

		# do cleanup for robostness
		self._cleanup()

	def onActive(self):
		obj = _SshClientObject()
		with open(self.pubkeyFile, "rt") as f:
			obj.userPubkey = f.read()
		self.sendObject(obj)

	def onInactive(self):
		self._cleanup()

	def onReject(self, rejectMessage):
		return

	def onRecv(self, dataObj):
		if dataObj.__class__.__name__ == "_SshServerObject":
			if not SnUtil.checkSshPubKey(dataObj.hostPubkeyEcdsa, "ecdsa", "root", self.getPeerName()):
				self.sendReject("invalid SshServerObject received")
				return

			cfgf = _CfgFileKnownHosts(self.knownHostsFile)
 			cfgf.addHost(self.getPeerName(), dataObj.hostPubkeyEcdsa)
		else:
			self.sendReject("invalid client data received")

	def _cleanup(self):
		cfgf = _CfgFileKnownHosts(self.knownHostsFile)
		cfgf.removeHost(self.getPeerName())

class _SshClientObject:
	userPubkey = None				# str

class _CfgFileKnownHosts:

	def __init__(self, filename):
		self.filename = filename
		self.lineList = []
		self.titleIndex = -1

	def touch(self):
		self._open()
		self._close()

	def addHost(self, hostName, pubkey):
		self._open()

		strList = pubkey.split()
		assert len(strList) == 3
		line = "%s %s %s"%(hostName, strList[0], strList[1])
		self.lineList.insert(self.titleIndex + 1, line)

		self._close()

	def removeHost(self, hostName):
		self._open()
		i = self.titleIndex + 1
		while i < len(self.lineList):
			line = self.lineList[i]
			if line == "\n":
				break
			if line.startswith("#"):
				i = i + 1
				continue
			strList = line.split()
			if len(strList) != 3:
				i = i + 1
				continue
			if strList[0] != hostName:
				i = i + 1
				continue
			self.lineList.pop(i)
		self._close()

	def _open(self):
		if not os.path.exists(self.filename):
			return

		# read file
		endIndex = -1
		with open(self.filename, "rt") as f:
			i = 0
			for line in f:
				self.lineList.append(line)
				if self.titleIndex == -1 and line == "# selfnet usr-server-ssh\n":
					self.titleIndex = i
				if self.titleIndex > 0 and endIndex == -1 and line == "\n":
					endIndex = i
				i = i + 1

		# last line of section must ends with "\n"
		if endIndex == -1 and len(self.lineList) > 0 and not self.lineList[-1].endswith("\n"):
			self.lineList[-1].append("\n")

		# need to create a section
		if self.titleIndex == -1:
			if len(self.lineList) > 0:
				self.lineList.append("\n")
			self.lineList.append("# selfnet usr-server-ssh\n")
			self.lineList.append("\n")
			self.titleIndex = len(self.lineList) - 2

	def _close(self):
		with open(self.filename, "wt") as f:
			for line in self.lineList:
				f.write(line)
		self.lineList = []
		self.titleIndex = -1

