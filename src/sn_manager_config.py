#!/usr/bin/python2
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import xml.sax.handler
import socket
import OpenSSL

class SnCfgGlobal:
	peerProbeInterval = None		# int, default is "1s"
	userBlackList = None			# list<str>

class SnCfgHostInfo:
	port = None						# int

class SnConfigManager:
	"""/etc/selfnetd
	    |----cert.pem							# mode 644
		|----privkey.pem						# mode 600
		|----ca-cert.pem						# mode 644
		|----ca-privkey.pem						# mode 600, only on the nexus machine
	    |----hosts.xml
	    |----selfnetd.conf"""

	def __init__(self, param):
		self.param = param
		self.cfgGlobal = None
		self.hostDict = None

		self._checkCertFiles()
		self._parseConfFile()		# fill self.cfgGlobal
		self._parseHostsFile()		# fill self.hostDict

	def getCfgGlobal(self):
		return self.cfgGlobal

	def getHostNameList(self):
		return self.hostDict.keys()

	def getHostInfo(self, hostName):
		if hostName == "localhost":
			return self.hostDict[socket.gethostname()]
		else:
			return self.hostDict[hostName]

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

class _ConfFileXmlHandler(xml.sax.handler.ContentHandler):
	INIT = 0
	IN_ROOT = 1
	IN_PEER_PROBE_INTERVAL = 2
	IN_USER_BLACKLIST = 3
	IN_USER_BLACKLIST_USER = 4

	def __init__(self, cfgGlobal):
		xml.sax.handler.ContentHandler.__init__(self)
		self.cfgGlobal = cfgGlobal
		self.state = self.INIT

	def startElement(self, name, attrs):
		if name == "root" and self.state == self.INIT:
			self.state = self.IN_ROOT
		elif name == "peer-probe-interval" and self.state == self.IN_ROOT:
			self.state = self.IN_PEER_PROBE_INTERVAL
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
		elif name == "user-blacklist" and self.state == self.IN_USER_BLACKLIST:
			self.state = self.IN_ROOT
		elif name == "user" and self.state == self.IN_USER_BLACKLIST_USER:
			self.state = self.IN_USER_BLACKLIST
		else:
			raise Exception("Failed to parse configuration file")

	def characters(self, content):
		if self.state == self.IN_PEER_PROBE_INTERVAL:
			self.cfgGlobal.peerProbeInterval = int(content)
		elif self.state == self.IN_USER_BLACKLIST_USER:
			self.cfgGlobal.userBlackList.append(content)
		else:
			pass

class _HostFileXmlHandler(xml.sax.handler.ContentHandler):
	INIT = 0
	IN_HOSTS = 1
	IN_HOST = 2
	IN_HOST_PORT = 3

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
		else:
			raise Exception("Failed to parse hosts file")

	def characters(self, content):
		if self.state == self.IN_HOST_PORT:
			self.curHostInfo.port = int(content)
		else:
			pass

def _newSnCfgGlobal():
	"""create new object, set default values"""

	cfgGlobal = SnCfgGlobal()
	cfgGlobal.peerProbeInterval = 1
	cfgGlobal.userBlackList = []
	return cfgGlobal

def _newSnCfgHostInfo():
	"""create new object, set default values"""

	curHostInfo = SnCfgHostInfo()
	curHostInfo.port = 2107
	curHostInfo.supportWakeOnLan = False
	curHostInfo.supportWakeOnWlan = False
	return curHostInfo

