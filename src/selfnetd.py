#!/usr/bin/python2
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import os
import sys
import shutil
from gi.repository import GLib
from dbus.mainloop.glib import DBusGMainLoop
from sn_util import SnUtil
from sn_param import SnParam
from sn_dbus import DbusMainObject

# create SnParam object
param = SnParam()
dbusMainObject = None
try:
	# create temp directory
	param.tmpDir = "/tmp/selfnetd"
	os.mkdir(param.tmpDir)

	# create main loop
	DBusGMainLoop(set_as_default=True)
	param.mainloop = GLib.MainLoop()

	# create managers
	param.configManager = SnConfigManager()
	param.peerManager = SnPeerManager()

	# create dbus root object
	dbusMainObject = DbusMainObject(param)

	# start main loop
	param.mainloop.run()
finally:
	if dbusMainObject is not None:
		dbusMainObject.release()
	if param.tmpDir is not None and os.path.exists(param.tmpDir):
		shutil.rmtree(param.tmpDir)

