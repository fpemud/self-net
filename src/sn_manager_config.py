#!/usr/bin/python2
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import os
import xml.sax.handler
import socket
import OpenSSL
from sn_util import SnUtil

class SnVersion:
	version = None					# str

	def __eq__(self, other):
		return isinstance(other, self.__class__) and self.version == other.version
	def __ne__(self, other):
		return not self.__eq__(other)
	def __hash__(self):
		return hash(self.version)

class SnCfgSerializationObject:
	strHostsXml = None				# str

	def __eq__(self, other):
		return isinstance(other, self.__class__) and self.strHostsXml == other.strHostsXml
	def __ne__(self, other):
		return not self.__eq__(other)
	def __hash__(self):
		return hash(self.strHostsXml)

class SnCfgHostInfo:
	port = None						# int
	isNexus = None					# bool

class SnCfgModuleInfo:
	enable = None					# bool
	moduleScope = None				# str
	moduleType = None				# str
	moduleId = None					# str

class SnConfigManager:
	"""/etc/selfnetd
	    |----cert.pem							# mode 644
		|----privkey.pem						# mode 600
		|----ca-cert.pem						# mode 644
		|----ca-privkey.pem						# mode 600, only on the nexus machine
	    |
	    |----selfnetd.conf
	    |----hosts.xml
	    |----modules.xml"""

	def __init__(self, param):
		self.param = param
		self.cfgGlobal = None
		self.hostDict = None
		self.moduleDict = None

		self._checkCertFiles()
		self._parseConfFile()		# fill self.cfgGlobal
		self._parseHostsFile()		# fill self.hostDict
		self._parseModulesFile()	# fill self.moduleDict

	def getVersion(self):
		ret = SnVersion()
		ret.version = "1.0.0"
		return ret

	def getCfgSerializationObject(self):
		ret = SnCfgSerializationObject()
		ret.strHostsXml = SnUtil.readFile(self.param.hostsFile)
		return ret

	def getPeerProbeInterval(self):
		return self.cfgGlobal.peerProbeInterval

	def getPeerKeepaliveInterval(self):
		return self.cfgGlobal.peerKeepaliveInterval

	def getUserBlackList(self):
		return self.cfgGlobal.userBlackList

	def getHostNameList(self):
		return self.hostDict.keys()

	def getHostInfo(self, hostName):
		if hostName == "localhost":
			return self.hostDict[socket.gethostname()]
		else:
			return self.hostDict[hostName]

	def getModuleNameList(self, moduleScope, moduleType):
		assert (moduleScope is None and moduleType is None) or (moduleScope is not None and moduleType is not None)

		ret = []
		for k, v in self.moduleDict.items():
			if moduleScope is not None:
				if v.moduleScope != moduleScope or v.moduleType != moduleType:
					continue
			ret.append(k)
		return ret

	def getModuleInfo(self, moduleName):
		return self.moduleDict[moduleName]

	def _checkCertFiles(self):
		# check CA certificate
		with open(self.param.caCertFile, 'r') as f:
			x509 = OpenSSL.crypto.load_certificate(OpenSSL.crypto.FILETYPE_PEM, f.read())
			if x509.has_expired():
				raise Exception("CA certificate has expired")

		# check certificate
		with open(self.param.certFile, 'r') as f:
			x509 = OpenSSL.crypto.load_certificate(OpenSSL.crypto.FILETYPE_PEM, f.read())
			if x509.has_expired():
				raise Exception("Certificate has expired")

			foundCommonName = False
			for item in x509.get_subject().get_components():
				if item[0] == "CN":
					if item[1] != socket.gethostname():
						raise Exception("Common name in certificate must equal to hostname")
					foundCommonName = True
					break
			if not foundCommonName:
				raise Exception("No common name in certificate")

	def _parseConfFile(self):
		# set default value
		self.cfgGlobal = _newSnCfgGlobal()

		# parse file
		h = _ConfFileXmlHandler(self.cfgGlobal)
		xml.sax.parse(self.param.confFile, h)

		# check parse result
		if self.cfgGlobal.peerProbeInterval < 1:
			raise Exception("Invalid cfgGlobal.peerProbeInterval")
		if self.cfgGlobal.peerKeepaliveInterval < 1:
			raise Exception("Invalid cfgGlobal.peerKeepaliveInterval")

	def _parseHostsFile(self):
		# set default value
		self.hostDict = dict()

		# parse file
		h = _HostFileXmlHandler(self.hostDict)
		xml.sax.parse(self.param.hostsFile, h)

		# check parse result
		if "localhost" in self.hostDict:
			raise Exception("Name \"localhost\" is reserved")

		if socket.gethostname() not in self.hostDict:
			raise Exception("No name for localhost in hosts file")

		if self.hostDict.values().count(lambda x: x.isNexus) > 1:
			raise Exception("There should be only zero or one nexus machine")

		if self.hostDict[socket.gethostname()].isNexus:
			if not os.path.exists(self.param.caPrivkeyFile):
				raise Exception("CA private key file should exist on nexus machine")
		else:
			if os.path.exists(self.param.caPrivkeyFile):
				raise Exception("CA private key file should not exist on non-nexus machine")

	def _parseModulesFile(self):
		# set default value
		self.moduleDict = dict()

		# parse file
		h = _ModuleFileXmlHandler(self. moduleDict)
		xml.sax.parse(self.param.modulesFile, h)

		# check parse result
		for m in self.moduleDict:
			exec("from %s import ModuleObject"%(m.replace("-", "_")))

class _SnCfgGlobal:
	peerProbeInterval = None		# int, default is "1s"
	peerKeepaliveInterval = None	# int, default is "1s"
	userBlackList = None			# list<str>

class _ConfFileXmlHandler(xml.sax.handler.ContentHandler):
	INIT = 0
	IN_ROOT = 1
	IN_PEER_PROBE_INTERVAL = 2
	IN_PEER_KEEPALIVE_INTERVAL = 3
	IN_USER_BLACKLIST = 4
	IN_USER_BLACKLIST_USER = 5

	def __init__(self, cfgGlobal):
		xml.sax.handler.ContentHandler.__init__(self)
		self.cfgGlobal = cfgGlobal
		self.state = self.INIT

	def startElement(self, name, attrs):
		if name == "root" and self.state == self.INIT:
			self.state = self.IN_ROOT
		elif name == "peer-probe-interval" and self.state == self.IN_ROOT:
			self.state = self.IN_PEER_PROBE_INTERVAL
		elif name == "peer-keepalive-interval" and self.state == self.IN_ROOT:
			self.state = self.IN_PEER_KEEPALIVE_INTERVAL
		elif name == "user-black-list" and self.state == self.IN_ROOT:
			self.state = self.IN_USER_BLACKLIST
		elif name == "user" and self.state == self.IN_USER_BLACKLIST:
			self.state = self.IN_USER_BLACKLIST_USER
		else:
			raise Exception("Failed to parse configuration file")

	def endElement(self, name):
		if name == "root" and self.state == self.IN_ROOT:
			self.state = self.INIT
		elif name == "peer-probe-interval" and self.state == self.IN_PEER_PROBE_INTERVAL:
			self.state = self.IN_ROOT
		elif name == "peer-keepalive-interval" and self.state == self.IN_PEER_KEEPALIVE_INTERVAL:
			self.state = self.IN_ROOT
		elif name == "user-blacklist" and self.state == self.IN_USER_BLACKLIST:
			self.state = self.IN_ROOT
		elif name == "user" and self.state == self.IN_USER_BLACKLIST_USER:
			self.state = self.IN_USER_BLACKLIST
		else:
			raise Exception("Failed to parse configuration file")

	def characters(self, content):
		if self.state == self.IN_PEER_PROBE_INTERVAL:
			self.cfgGlobal.peerProbeInterval = int(content)
		elif self.state == self.IN_PEER_KEEPALIVE_INTERVAL:
			self.cfgGlobal.peerKeepaliveInterval = int(content)
		elif self.state == self.IN_USER_BLACKLIST_USER:
			self.cfgGlobal.userBlackList.append(content)
		else:
			pass

class _HostFileXmlHandler(xml.sax.handler.ContentHandler):
	INIT = 0
	IN_HOSTS = 1
	IN_HOST = 2
	IN_HOST_PORT = 3
	IN_HOST_NEXUS = 4

	def __init__(self, hostDict):
		xml.sax.handler.ContentHandler.__init__(self)
		self.hostDict = hostDict
		self.curHostName = None
		self.curHostInfo = None
		self.state = self.INIT

	def startElement(self, name, attrs):
		if name == "hosts" and self.state == self.INIT:
			self.state = self.IN_HOSTS
		elif name == "host" and self.state == self.IN_HOSTS:
			self.state = self.IN_HOST
			self.curHostName = attrs["name"]
			self.curHostInfo = _newSnCfgHostInfo()
		elif name == "port" and self.state == self.IN_HOST:
			self.state = self.IN_HOST_PORT
		elif name == "nexus" and self.state == self.IN_HOST:
			self.state = self.IN_HOST_NEXUS
			self.curHostInfo.isNexus = True
		else:
			raise Exception("Failed to parse hosts file")

	def endElement(self, name):
		if name == "hosts" and self.state == self.IN_HOSTS:
			self.state = self.INIT
		elif name == "host" and self.state == self.IN_HOST:
			self.hostDict[self.curHostName] = self.curHostInfo
			self.curHostName = None
			self.curHostInfo = None
			self.state = self.IN_HOSTS
		elif name == "port" and self.state == self.IN_HOST_PORT:
			self.state = self.IN_HOST
		elif name == "nexus" and self.state == self.IN_HOST_NEXUS:
			self.state = self.IN_HOST
		else:
			raise Exception("Failed to parse hosts file")

	def characters(self, content):
		if self.state == self.IN_HOST_PORT:
			self.curHostInfo.port = int(content)
		else:
			pass

class _ModuleFileXmlHandler(xml.sax.handler.ContentHandler):
	INIT = 0
	IN_MODULES = 1
	IN_MODULE = 2
	IN_MODULE_ENABLE = 3

	def __init__(self, moduleDict):
		xml.sax.handler.ContentHandler.__init__(self)
		self.moduleDict = moduleDict
		self.curModuleName = None
		self.curModuleInfo = None
		self.state = self.INIT

	def startElement(self, name, attrs):
		if name == "modules" and self.state == self.INIT:
			self.state = self.IN_MODULES
		elif name == "module" and self.state == self.IN_MODULES:
			self.state = self.IN_MODULE
			self.curModuleName = attrs["name"]
			self.curModuleInfo = _newSnCfgModuleInfo(self.curModuleName)
		elif name == "enable" and self.state == self.IN_MODULE:
			self.state = self.IN_MODULE_ENABLE
		else:
			raise Exception("Failed to parse modules file")

	def endElement(self, name):
		if name == "modules" and self.state == self.IN_MODULES:
			self.state = self.INIT
		elif name == "module" and self.state == self.IN_MODULE:
			self.moduleDict[self.curModuleName] = self.curModuleInfo
			self.curModuleName = None
			self.curModuleInfo = None
			self.state = self.IN_MODULES
		elif name == "enable" and self.state == self.IN_MODULE_ENABLE:
			self.state = self.IN_MODULE
		else:
			raise Exception("Failed to parse modules file")

	def characters(self, content):
		if self.state == self.IN_MODULE_ENABLE:
			self.curModuleInfo.enable = bool(content)
		else:
			pass

def _newSnCfgGlobal():
	"""create new object, set default values"""

	cfgGlobal = _SnCfgGlobal()
	cfgGlobal.peerProbeInterval = 1
	cfgGlobal.peerKeepaliveInterval = 1
	cfgGlobal.userBlackList = []
	return cfgGlobal

def _newSnCfgHostInfo():
	"""create new object, set default values"""

	curHostInfo = SnCfgHostInfo()
	curHostInfo.port = 2107
	curHostInfo.isNexus = False
	curHostInfo.supportWakeOnLan = False
	curHostInfo.supportWakeOnWlan = False
	return curHostInfo

def _newSnCfgModuleInfo(moduleName):
	"""create new object, set default values"""

	curModuleInfo = SnCfgModuleInfo()
	curModuleInfo.enable = False

	strList = moduleName.split("-")
	curModuleInfo.moduleScope = strList[0]
	curModuleInfo.moduleType = strList[1]
	curModuleInfo.moduleId = strList[2]

	return curModuleInfo

