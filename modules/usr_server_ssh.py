#!/usr/bin/python2
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import os
from sn_util import SnUtil
from sn_module import SnModule
from sn_module import SnModuleInstance

class ModuleObject(SnModule):

	def getModuleName(self):
		return "usr-server-ssh"

	def getPropDict(self):
		ret = dict()
		ret["allow-local-peer"] = True
		return ret

class ModuleInstanceObject(SnModuleInstance):

	def onInit(self):
		self.sshDir = os.path.expanduser("~%s/.ssh"%(self.getUserName()))
		self.authkeysFile = os.path.join(self.sshDir, "authorized_keys")

		# initialize config files
		if not os.path.exists(self.authkeysFile):
			SnUtil.mkDir(self.sshDir)
			SnUtil.touchFile(self.authkeysFile)
		self._cleanup()

	def onActive(self):
		return

	def onInactive(self):
		self._cleanup()
		return

	def onReject(self, rejectMessage):
		self._cleanup()
		return

	def onRecv(self, dataObj):
		if dataObj.__class__.__name__ == "_SshClientObject":
			if not self._checkPubKey(dataObj.pubkey):
				self.reject("invalid SshClientObject received")
				return

			cfgf = _CfgFileAuthorizedKeys(self.authkeysFile)
			cfgf.addPubKey(dataObj.pubkey)
			return
		else:
			self.reject("invalid client data received")
			return

	def _checkPubKey(self, pubkey):
		strList = pubkey.split()
		if len(strList) != 3:
			return False
		if strList[0] != "ssh-rsa":
			return False
		if strList[2] != "%s@%s"%(self.getUserName(), self.getPeerName()):
			return False

	def _cleanup(self):
		cfgf = _CfgFileAuthorizedKeys(self.authkeysFile)
		cfgf.removePubKey(self.getUserName(), self.getPeerName())

class _CfgFileAuthorizedKeys:

	def __init__(self, filename):
		self.filename = filename
		self.lineList = []
		self.titleIndex = -1

	def addPubKey(self, pubkey):
		self._open()
		self.lineList.insert(self.titleIndex + 1, pubkey)
		self._close()

	def removePubKey(self, userName, hostName):
		self._open()
		i = self.titleIndex + 1
		while i < len(self.lineList):
			line = self.lineList[i]
			if line == "\n":
				break
			if line.startswith("#"):
				continue
			strList = line.split()
			if len(strList) != 3:
				continue
			if strList[2] == "%s@%s\n"%(userName, hostName):
				self.lineList.pop(i)
				i = i - 1
		self._close()

	def _open(self):
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

