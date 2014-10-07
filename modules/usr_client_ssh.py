#!/usr/bin/python3
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
		ret["standalone"] = False
		return ret


class ModuleInstanceObject(SnModuleInstance):

	def onInit(self):
		self.sshDir = os.path.expanduser("~%s/.ssh" % (self.getUserName()))
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
			obj.userPubkey = f.readline().rstrip("\n")
		self.sendObject(obj)

	def onInactive(self):
		self._cleanup()

	def onRecv(self, dataObj):
		if dataObj.__class__.__name__ == "_SshServerObject":
			if not SnUtil.checkSshPubKey(dataObj.hostPubkeyEcdsa, "ecdsa", "root", self.getPeerName()):
				raise SnRejectException("invalid SshServerObject received")

			nameList = [self.getPeerName()]
			if self.isLocalPeer():
				nameList.append("localhost")
				nameList += dataObj.addrList
				for i in range(1, 256):
					nameList.append("127.0.0.%d" % (i))
			else:
				nameList += dataObj.addrList

			cfgf = _CfgFileKnownHosts(self.knownHostsFile)
			cfgf.load()
			cfgf.addHost(nameList, dataObj.hostPubkeyEcdsa)
			cfgf.save()
		else:
			raise SnRejectException("invalid client data received")

	def _cleanup(self):
		cfgf = _CfgFileKnownHosts(self.knownHostsFile)
		cfgf.load()
		cfgf.removeHost(self.getPeerName())
		cfgf.save()


class _SshClientObject:
	userPubkey = None				# str


class _CfgFileKnownHosts:

	def __init__(self, filename):
		self.filename = filename
		self.lineList = []

	def touch(self):
		self.load()
		self.save()

	def load(self):
		"""load/save is not open/close, no need to put them in try block"""

		if not os.path.exists(self.filename):
			return

		titleIndex = -1
		with open(self.filename, "rt") as f:
			i = 0
			for line in f:
				self.lineList.append(line)
				if titleIndex == -1 and line == "# selfnet usr-server-ssh\n":
					titleIndex = i
				i = i + 1

		if titleIndex == -1:
			self.lineList.append("# selfnet usr-server-ssh\n")
			self.lineList.append("# selfnet usr-server-ssh end\n")
			self.lineList.append("\n")

	def save(self):
		with open(self.filename, "wt") as f:
			for line in self.lineList:
				f.write(line)
		self.lineList = []

	def addHost(self, nameList, pubkey):
		prefix = ",".join(nameList)
		strList = pubkey.split()
		assert len(strList) == 3
		line = "%s %s %s\n" % (prefix, strList[0], strList[1])

		for i in range(0, len(self.lineList)):
			if self.lineList[i] == "# selfnet usr-server-ssh\n":
				self.lineList.insert(i + 1, line)
				break

	def removeHost(self, firstName):
		i = 0
		while i < len(self.lineList):
			if self.lineList[i] == "# selfnet usr-server-ssh\n":
				i = i + 1
				break

		while i < len(self.lineList):
			line = self.lineList[i]
			if line == "# selfnet usr-server-ssh end\n":
				break
			if line.startswith("#"):
				i = i + 1
				continue
			strList = line.split()
			if len(strList) != 3:
				i = i + 1
				continue
			if strList[0].split(",")[0] != firstName:
				i = i + 1
				continue
			self.lineList.pop(i)
