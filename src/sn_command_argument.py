#!/usr/bin/python2
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import os
import sys

class SnCommandArgument:

	def __init__(self):
		# set default values
		self.subcmd = None						# "", "generate_ca_cert", "generate_cert"
		self.daemonize = None					# bool
		self.debug_level = None					# "CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"
		self.hostname = None					# str
		self.out_dir = None						# str
		self.export = None						# bool

		# do parsing
		assert len(sys.argv) >= 1
		if len(sys.argv) == 1:
			self.subcmd = ""
			self._parseSubCmdEmpty()
		elif sys.argv[1] == "generate_ca_cert":
			self.subcmd = "generate_ca_cert"
			self._parseSubCmdGenCaCert()
		elif sys.argv[1] == "generate_cert":
			self.subcmd = "generate_cert"
			self._parseSubCmdGenCert()
		else:
			self.subcmd = ""
			self._parseSubCmdEmpty()

	def _parseSubCmdEmpty(self):
		self.daemonize = True
		self.debug_level = "WARNING"

		i = 1
		while i < len(sys.argv):
			if sys.argv[i] == "-D":
				self.daemonize = False
				i = i + 1
			elif sys.argv[i] == "-d":
				if i == len(sys.argv) - 1:
					raise Exception("-d should be followed by debug level")
				if sys.argv[i + 1] not in ["CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"]:
					raise Exception("invalid debug level")
				self.debug_level = sys.argv[i + 1]
				i = i + 2
			else:
				raise Exception("invalid argument \"%s\""%(sys.argv[i]))

	def _parseSubCmdGenCaCert(self):
		if len(sys.argv) > 2:
			raise Exception("too many arguments")

	def _parseSubCmdGenCert(self):
		self.hostname = None
		self.out_dir = os.getcwd()
		self.export = False

		i = 2
		while i < len(sys.argv):
			if sys.argv[i] == "--hostname":
				if i == len(sys.argv) - 1:
					raise Exception("--hostname should be followed by hostname")
				self.hostname = sys.argv[i + 1]
				i = i + 2
			elif sys.argv[i] == "--outdir":
				if i == len(sys.argv) - 1:
					raise Exception("--outdir should be followed by a directory path")
				self.out_dir = sys.argv[i + 1]
				i = i + 2
			elif sys.argv[i] == "--export":
				self.export = True
				i = i + 1
			else:
				raise Exception("invalid argument \"%s\""%(sys.argv[i]))

		if self.hostname is None:
			raise Exception("no hostname specified")

