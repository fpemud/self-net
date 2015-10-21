#!/usr/bin/python3
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import dbus
import dbus.service
from sn_manager_local import SnLocalManager
from sn_manager_peer import SnPeerManager

################################################################################
# DBus API Docs
################################################################################
#
# ==== Main Application ====
# Service               org.fpemud.SelfNet
# Interface             org.fpemud.SelfNet
# Object path           /
#
# Methods:
# str                 GetWorkState()
# array<peerId:int>   GetPeerList()
# peerId:int          GetPeer(peerName:str)
#
# Signals:
# WorkStateChanged(newWorkState:str)
#
# ==== Peer ====
# Service               org.fpemud.SelfNet
# Interface             org.fpemud.SelfNet.Peer
# Object path           /Peers/{peerId:int}
#
# Methods:
# str               GetName()
# str               GetPowerState()
# void              DoPowerOperation(opName:str)
#
# Signals:
# PowerStateChanged(newPowerState:str)
#


class DbusMainObject(dbus.service.Object):

    def __init__(self, param):
        self.param = param
        self.peerList = []
        self.moduleList = []

        # initialize peer list
        i = 0
        for pn in self.param.peerManager.getPeerNameList():
            po = DbusPeerObject(self.param, i, pn)
            self.peerList.append(po)
            i = i + 1

        # register dbus object path
        bus_name = dbus.service.BusName('org.fpemud.SelfNet', bus=dbus.SystemBus())
        dbus.service.Object.__init__(self, bus_name, '/org/fpemud/SelfNet')

    def release(self):
        self.remove_from_connection()

    @dbus.service.method('org.fpemud.SelfNet', in_signature='', out_signature='s')
    def GetWorkState(self):
        ws = self.param.localManager.getWorkState()
        if ws == SnLocalManager.WORK_STATE_IDLE:
            return "idle"
        elif ws == SnLocalManager.WORK_STATE_WORKING:
            return "working"
        else:
            assert False

    @dbus.service.method('org.fpemud.SelfNet', in_signature='', out_signature='ai')
    def GetPeerList(self):
        ret = []
        for po in self.peerList:
            ret.append(po.peerId)
        return ret

    @dbus.service.method('org.fpemud.SelfNet', in_signature='s', out_signature='i')
    def GetPeer(self, peerName):
        for po in self.peerList:
            if peerName == po.peerName:
                return po.peerId
        return -1

    @dbus.service.signal('org.fpemud.SelfNet', signature='s')
    def WorkStateChanged(self, newWorkState):
        pass

    @dbus.service.method('org.fpemud.SelfNet', in_signature='', out_signature='a{s(ss)}')
    def DebugGetModuleInfo(self):
        return self.param.localManager.debugGetModuleInfo()


class DbusPeerObject(dbus.service.Object):

    def __init__(self, param, peerId, peerName):
        self.param = param
        self.peerId = peerId
        self.peerName = peerName

        # register dbus object path
        bus_name = dbus.service.BusName('org.fpemud.SelfNet', bus=dbus.SystemBus())
        dbus.service.Object.__init__(self, bus_name, '/org/fpemud/SelfNet/Peers/%d' % (self.peerId))

    def release(self):
        self.remove_from_connection()

    @dbus.service.method('org.fpemud.SelfNet.Peer', sender_keyword='sender', in_signature='', out_signature='s')
    def GetName(self, sender=None):
        return self.peerName

    @dbus.service.method('org.fpemud.SelfNet.Peer', sender_keyword='sender', in_signature='', out_signature='s')
    def GetPowerState(self, sender=None):
        powerStateDict = {
            SnPeerManager.POWER_STATE_UNKNOWN: "unknown",
            SnPeerManager.POWER_STATE_POWEROFF: "poweroff",
            SnPeerManager.POWER_STATE_REBOOTING: "rebooting",
            SnPeerManager.POWER_STATE_SUSPEND: "suspend",
            SnPeerManager.POWER_STATE_HIBERNATE: "hibernate",
            SnPeerManager.POWER_STATE_HYBRID_SLEEP: "hybrid-sleep",
            SnPeerManager.POWER_STATE_RUNNING: "running",
        }
        powerState = self.param.peerManager.getPeerPowerState(self.peerName)
        return powerStateDict[powerState]

    @dbus.service.method('org.fpemud.SelfNet.Peer', sender_keyword='sender', in_signature='s', out_signature='', async_callbacks=('reply_handler', 'error_handler'))
    def DoPowerOperation(self, opName, reply_handler, error_handler, sender=None):
        if opName not in ["poweron", "poweroff", "reboot", "wakeup", "suspend", "hibernate", "hybrid-sleep"]:
            error_handler(Exception("invalid power operation name \"%s\"" % (opName)))
            return
        self.param.peerManager.doPeerPowerOperationAsync(self.peerName, str(opName), reply_handler, error_handler)

    @dbus.service.signal('org.fpemud.SelfNet.Peer', signature='s')
    def PowerStateChanged(self, newPowerState):
        pass
