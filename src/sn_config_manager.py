#!/usr/bin/python2
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import socket
import OpenSSL

class SnCfgGlobal:
	peerProbeInterval = None		# int, default is 1s

class SnCfgHostInfo:
	port = None						# int

class SnConfigManager(GObject.GObject):
	"""/etc/selfnetd
	    |----cert.pem							# mode 644
		|----privkey.pem						# mode 600
		|----ca-cert.pem						# mode 644
		|----ca-privkey.pem						# mode 600, only on the nexus machine
	    |----hosts.xml
	    |----selfnetd.conf"""

	def __init__(self, param):
		GObject.GObject.__init__(self)

		self.param = param
		self.cfgGlobal = SnCfgGlobal()
		self.hostDict = dict()

		self._checkCertFiles()
		self._parseConfFile()
		self._parseHostsFile()

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
		x509 = OpenSSL.crypto.load_certificate(OpenSSL.crypto.FILETYPE_PEM, self.param.caCertFile)
		if x509.has_expired():
			raise Exception("CA certificate has expired")

		# check certificate
		x509 = OpenSSL.crypto.load_certificate(OpenSSL.crypto.FILETYPE_PEM, self.param.certFile)
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
		self.cfgGlobal.peerProbeInterval = 1

		# create parser class
		class thehandler(xml.sax.handler.ContentHandler):
			INIT = 0
			IN_PEER_PROBE_INTERVAL = 1

			def __init__(self, cfgGlobal):
				self.cfgGlobal = cfgGlobal
				self.state = INIT

			def startElement(self, name, attrs):
				if name == "peer-probe-interval" and self.state == INIT:
					self.state = IN_PEER_PROBE_INTERVAL
				else:
					raise Exception("Failed to parse configuration file")

			def endElement(self, name, attrs):
				if name == "peer-probe-interval" and self.state == IN_PEER_PROBE_INTERVAL:
					self.state = INIT
				else:
					raise Exception("Failed to parse configuration file")

			def characters(self, content):
				if self.stat == IN_HOST_PORT:
					self.cfgGlobal.peerProbeInterval = int(content)
				else:
					raise Exception("Failed to parse configuration file")

		# parse file
		h = thehandler()
		xml.sax.parse(self.param.confFile, h)

		# check parse result
		if self.cfgGlobal.peerProbeInterval < 1:
			raise Exception("Invalid cfgGlobal.peerProbeInterval")

	def _parseHostsFile(self):
		# create parser class
		class thehandler(xml.sax.handler.ContentHandler):
			INIT = 0
			IN_HOST = 1
			IN_HOST_PORT = 2

			def __init__(self, hostDict):
				self.hostDict = hostDict
				self.curHostName = None
				self.curHostInfo = None
				self.state = INIT

			def startElement(self, name, attrs):
				if name == "host" and self.state == INIT:
					self.state = IN_HOST:
					self.curHostName = attrs["name"]
					self.curHostInfo = SnCfgHostInfo()
				elif name == "port" and self.state == IN_HOST:
					self.state = IN_HOST_PORT
				else:
					raise Exception("Failed to parse hosts file")

			def endElement(self, name, attrs):
				if name == "host" and self.state == IN_HOST:
					self.hostDict[self.curHostName] = self.curHostInfo
					self.curHostName = None
					self.curHostInfo = None
					self.state = INIT
				elif name == "port" and self.state == IN_HOST_PORT:
					self.state = IN_HOST
				else:
					raise Exception("Failed to parse hosts file")

			def characters(self, content):
				if self.stat == IN_HOST_PORT:
					self.curHostInfo.port = int(content)
				else:
					raise Exception("Failed to parse hosts file")

		# parse file
		h = thehandler()
		xml.sax.parse(self.param.hostsFile, h)

		# check parse result
		if "localhost" in self.hostDict:
			raise Exception("Name \"localhost\" is reserved")
		if socket.gethostname() not in self.hostDict:
			raise Exception("No name for localhost in hosts file")

