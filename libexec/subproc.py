#!/usr/bin/python2
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import os
import sys
import shutil
import tempfile
import logging
import argparse
from daemon import daemon
from daemon import pidfile
from gi.repository import GLib
from dbus.mainloop.glib import DBusGMainLoop

sys.path.append('/usr/lib/selfnetd')
sys.path.append('/usr/lib/selfnetd/modules')		# fixme
from sn_util import SnUtil
from sn_param import SnParam
from sn_manager_config import SnConfigManager
from sn_manager_local import SnLocalManager
from sn_manager_peer import SnPeerManager
from sn_dbus import DbusMainObject

def parseArgs():
	argParser = argparse.ArgumentParser()
	argParser.add_argument("--no-daemon", dest='daemonize', action="store_false", default=True,
		help="Do not daemonize.")
	argParser.add_argument("--pid-file", dest='pid_file', help="Specify location of a PID file.")
	argParser.add_argument("-d", "--debug-level", dest='debug_level',
		choices=['CRITICAL', 'ERROR', 'WARNING', 'INFO', 'DEBUG'], default="WARNING",
		help="Set output debug message level")
	return argParser.parse_args()

################################################################################

parseResult = parseArgs()

# initialize SnParam
param = SnParam()
if parseResult.pid_file is not None:
	self.pidFile = parseResult.pid_file

try:
	# create directory
	SnUtil.mkDir(param.logDir)
	SnUtil.mkDirAndClear(param.runDir)
	param.tmpDir = tempfile.mkdtemp(prefix="selfnetd-")

	# set logging parameter
	if parseResult.daemonize:
		logging.getLogger().addHandler(logging.FileHandler(param.logFile))
	else:
		logging.getLogger().addHandler(logging.StreamHandler(sys.stderr))

	if parseResult.debug_level is not None:
		if parseResult.debug_level == "CRITICAL":
			logLevel = logging.CRITICAL
		elif parseResult.debug_level == "ERROR":
			logLevel = logging.ERROR
		elif parseResult.debug_level == "WARNING":
			logLevel = logging.WARNING
		elif parseResult.debug_level == "INFO":
			logLevel = logging.INFO
		elif parseResult.debug_level == "DEBUG":
			logLevel = logging.DEBUG
		else:
			assert False
		logging.getLogger().setLevel(logLevel)

	logging.debug("selfnetd: Start")

	# daemonize
	dc = None
	if parseResult.daemonize:
		pidf = pidfile.PIDLockFile(param.pidFile)
		dc = daemon.DaemonContext(pidfile=pidf)
		dc.open()

	try:
		logging.info("selfnetd: Initializaition starts")

		# create main loop
		DBusGMainLoop(set_as_default=True)
		param.mainloop = GLib.MainLoop()

		# create managers
		param.configManager = SnConfigManager(param)
		param.localManager = SnLocalManager(param)
		param.peerManager = SnPeerManager(param)

		# create dbus root object
		param.dbusMainObject = DbusMainObject(param)

		# start main loop
		logging.info("selfnetd: Mainloop begins")
		param.mainloop.run()
		logging.info("selfnetd: Mainloop exits")
	finally:
		if param.dbusMainObject is not None:
 			param.dbusMainObject.release()
 		if param.peerManager is not None:
			param.peerManager.dispose()
			param.peerManager = None
		if param.localManager is not None:
			param.localManager.dispose()
			param.localManager = None
		if param.configManager is not None:
			param.configManager.dispose()
			param.configManager = None
		logging.info("selfnetd: Finalization completes")
		logging.shutdown()
		if dc is not None:
			dc.close()
finally:
	# shouldn't remove log directory
	if param.tmpDir is not None and os.path.exists(param.tmpDir):
		shutil.rmtree(param.tmpDir)
	if os.path.exists(param.runDir):
		shutil.rmtree(param.runDir)

