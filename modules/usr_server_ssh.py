#!/usr/bin/python2
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import os
import netifaces
from sn_util import SnUtil
from sn_module import SnModule
from sn_module import SnModuleInstance
from sn_module import SnModuleInstanceInitException

class ModuleObject(SnModule):

	def getModuleName(self):
		return "usr-server-ssh"

	def getPropDict(self):
		ret = dict()
		ret["allow-local-peer"] = True
		ret["suid"] = False
		return ret

class ModuleInstanceObject(SnModuleInstance):

	def onInit(self):
		self.sshSysDir = "/etc/ssh"
		self.sshSysRsaPrivFile = os.path.join(self.sshSysDir, "ssh_host_rsa_key")
		self.sshSysRsaPubFile = os.path.join(self.sshSysDir, "ssh_host_rsa_key.pub")
		self.sshSysDsaPrivFile = os.path.join(self.sshSysDir, "ssh_host_dsa_key")
		self.sshSysDsaPubFile = os.path.join(self.sshSysDir, "ssh_host_dsa_key.pub")
		self.sshSysEcdsaPrivFile = os.path.join(self.sshSysDir, "ssh_host_ecdsa_key")
		self.sshSysEcdsaPubFile = os.path.join(self.sshSysDir, "ssh_host_ecdsa_key.pub")

		self.sshDir = os.path.expanduser("~%s/.ssh"%(self.getUserName()))
		self.authkeysFile = os.path.join(self.sshDir, "authorized_keys")

		# check server configuration
		self._checkServerCfg()

		# initialize user auth-keys files
		SnUtil.mkDir(self.sshDir)
		_CfgFileAuthorizedKeys(self.authkeysFile).touch()

		# do cleanup for robostness
		self._cleanup()

	def onActive(self):
		obj = _SshServerObject()
		obj.addrList = self._getAddrList()
		with open(self.sshSysRsaPubFile, "rt") as f:
			obj.hostPubkeyRsa = f.read()
		with open(self.sshSysDsaPubFile, "rt") as f:
			obj.hostPubkeyDsa = f.read()
		with open(self.sshSysEcdsaPubFile, "rt") as f:
			obj.hostPubkeyEcdsa = f.read()
		self.sendObject(obj)

	def onInactive(self):
		self._cleanup()

	def onReject(self, rejectMessage):
		return

	def onRecv(self, dataObj):
		if dataObj.__class__.__name__ == "_SshClientObject":
			if not SnUtil.checkSshPubKey(dataObj.userPubkey, "rsa", self.getUserName(), self.getPeerName()):
				self.sendReject("invalid SshClientObject received")
				return

			cfgf = _CfgFileAuthorizedKeys(self.authkeysFile)
			cfgf.addPubKey(dataObj.userPubkey)
		else:
			self.sendReject("invalid client data received")

	def _cleanup(self):
		cfgf = _CfgFileAuthorizedKeys(self.authkeysFile)
		cfgf.removePubKey(self.getUserName(), self.getPeerName())

	def _checkServerCfg(self):
		if not os.path.exists(self.sshSysRsaPrivFile):
			raise SnModuleInstanceInitException("server rsa private key file does not exist")
		if not os.path.exists(self.sshSysRsaPubFile):
			raise SnModuleInstanceInitException("server rsa public key file does not exist")
		with open(self.sshSysRsaPubFile, "rt") as f:
			pubkey = f.read()
			if not SnUtil.checkSshPubKey(pubkey, "rsa", "root", self.getHostName()):
				raise SnModuleInstanceInitException("server rsa public key file is invalid")
				
		if not os.path.exists(self.sshSysDsaPrivFile):
			raise SnModuleInstanceInitException("server dsa private key file does not exist")
		if not os.path.exists(self.sshSysDsaPubFile):
			raise SnModuleInstanceInitException("server dsa private key file does not exist")
		with open(self.sshSysDsaPubFile, "rt") as f:
			pubkey = f.read()
			if not SnUtil.checkSshPubKey(pubkey, "dsa", "root", self.getHostName()):
				raise SnModuleInstanceInitException("server dsa public key file is invalid")

		if not os.path.exists(self.sshSysEcdsaPrivFile):
			raise SnModuleInstanceInitException("server ecdsa private key file does not exist")
		if not os.path.exists(self.sshSysEcdsaPubFile):
			raise SnModuleInstanceInitException("server ecdsa private key file does not exist")
		with open(self.sshSysEcdsaPubFile, "rt") as f:
			pubkey = f.read()
			if not SnUtil.checkSshPubKey(pubkey, "ecdsa", "root", self.getHostName()):
				raise SnModuleInstanceInitException("server ecdsa public key file is invalid")

	def _getAddrList(self):
		ret = []
		for ifname in netifaces.interfaces():
			if ifname == "lo":
				continue
			if netifaces.AF_INET in netifaces.ifaddresses(ifname):
				for link in netifaces.ifaddresses(ifname)[netifaces.AF_INET]:
					if "addr" in link:
						ret.append(link["addr"])
#			if netifaces.AF_INET6 in netifaces.ifaddresses(ifname):
#				for link in netifaces.ifaddresses(ifname)[netifaces.AF_INET6]:
#					if "addr" in link:
#						ret.append(link["addr"])
		return ret

class _SshServerObject:
	hostAddrList = None					# list<str>
	hostPubkeyRsa = None				# str
	hostPubkeyDsa = None				# str
	hostPubkeyEcdsa = None				# str

class _CfgFileAuthorizedKeys:

	def __init__(self, filename):
		self.filename = filename
		self.lineList = []

	def touch(self):
		self._open()
		self._close()

	def addPubKey(self, pubkey):
		self._open()

		for i in range(0, len(self.lineList)):
			if self.lineList[i] == "# selfnet usr-server-ssh\n":
				self.lineList.insert(i + 1, pubkey + "\n")
				break

		self._close()

	def removePubKey(self, userName, hostName):
		self._open()

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
			if strList[2] != "%s@%s"%(userName, hostName):
				i = i + 1
				continue
			self.lineList.pop(i)

		self._close()

	def _open(self):
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

	def _close(self):
		with open(self.filename, "wt") as f:
			for line in self.lineList:
				f.write(line)
		self.lineList = []

