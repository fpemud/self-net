#!/usr/bin/python3
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import os
import sys
import fcntl
import struct
import pickle
import logging
import traceback
from gi.repository import GLib

sys.path.append('/usr/lib/selfnetd')
sys.path.append('/usr/lib/selfnetd/modules')		# fixme
from sn_util import SnUtil
from sn_util import StdinStdoutObjSocket


"""
new-module message:
    {
        "type": "new-module",
        "username": USERNAME,    # doesn't exist for system
        "properties": {
            FROM-PROPERTY-XML,
        },
        "peer-host-id": HOST-ID,        # optional, depends on module instancing mode
        "peer-app-id": APP-ID,          # optional, depends on module instancing mode
    }

delete-module message:
    {
        "type": "delete-module",
        "username": USERNAME,    # doesn't exist for system
        "properties": {
            FROM-PROPERTY-XML,
        },
        "peer-host-id": HOST-ID,        # optional, depends on module instancing mode
        "peer-app-id": APP-ID,          # optional, depends on module instancing mode
    }

data message:
    {
        "type": "data",
        "username": USERNAME,       # doesn't exist for system
        "app-id": APP-ID,
        "peer-host-id": HOST-ID,
        "peer-app-id": APP-ID,
        "data": DATA,
    }
"""


class WorkerProc:

    def __init__(self, param):
        self.tmpDir = param["tmpDir"]
        self.connSock = StdinStdoutObjSocket(self.onConnRecv)

    def onConnRecv(self, sock, message):
        assert sock == self.connSock
        assert isinstance(data, dict)

        if message["type"] == "new-module":
            self.newModule()
            return

        if message["type"] == "delete-module":
            self.deleteModule()
            return

        if message["type"] == "data":
            self.dataReceived()
            return

        assert False

    def newModule(self):
        logging.debug("WorkerProc.newModule: Start")
        logging.debug("WorkerProc.newModule: End")

    def deleteModule(self):
        logging.debug("WorkerProc.deleteModule: Start")
        logging.debug("WorkerProc.deleteModule: End")

    def dataReceived(self):
        logging.debug("WorkerProc.dataReceived: Start")
        logging.debug("WorkerProc.dataReceived: End")


def _type_check(obj, typeobj):
    return str(obj.__class__) == str(typeobj)


################################################################################


assert len(sys.argv) == 2
param = json.loads(sys.argv[1])

logging.getLogger().addHandler(logging.FileHandler(param["logFile"]))
logging.getLogger().setLevel(SnUtil.getLoggingLevel(param["logLevel"]))

# do work
logging.info("selfnetd-plugin-proc: Mainloop begins")
procObj = None
try:
    if "userName" in param:
        SnUtil.dropPriviledgeTo(param["userName"])    # drop priviledge
    procObj = WorkerProc(param)
    GLib.MainLoop().run()
except Exception as e:
    logging.error(traceback.format_exc())
    sys.exit(1)
finally:
    if procObj is not None:
        pass                    # WorkerProc object does not need to be disposed
    logging.info("selfnetd-plugin-proc: Mainloop exits")
