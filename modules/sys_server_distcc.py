#!/usr/bin/python3
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import os
from sn_module import SnModule
from sn_module import SnModuleInstance


class ModuleObject(SnModule):

    def getModuleName(self):
        return "sys-server-distcc"

    def getPropDict(self):
        ret = dict()
        ret["allow-local-peer"] = False
        ret["suid"] = False
        ret["standalone"] = False
        return ret


class ModuleInstanceObject(SnModuleInstance):

    def onInit(self):
        self.cfgDir = "/etc/distcc"
        if not os.path.isdir(self.cfgDir):
            raise Exception("distcc configuration directory does not exist")

        return

    def onActive(self):
        # send sys param to client
        obj = _DistccServerObject()
        obj.jobNumber = 4
        self.sendObject(obj)

    def onInactive(self):
        return

    def onRecv(self, dataObj):
        raise SnRejectException("receive client data")


class _DistccServerObject:
    jobNumber = None				# int
