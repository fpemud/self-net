#!/usr/bin/python3
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import os
import dbus
import random
import zipfile
from OpenSSL import crypto
from sn_util import SnUtil


class SnSubCmdMain:

    def __init__(self, param):
        self.param = param

    def generateCaCert(self):
        # generate certificate and private key
        k = crypto.PKey()
        k.generate_key(crypto.TYPE_RSA, 1024)

        cert = crypto.X509()
        cert.get_subject().CN = "selfnet"
        cert.set_serial_number(random.randint(0, 65535))
        cert.gmtime_adj_notBefore(0)
        cert.gmtime_adj_notAfter(36500 * 24 * 3600)
        cert.set_issuer(cert.get_subject())
        cert.set_pubkey(k)
        cert.sign(k, 'sha1')

        # save certificate and private key
        self._dumpCertAndKey(cert, k, self.param.caCertFile, self.param.caPrivkeyFile)

    def generateCert(self, hostname, outDir, isExport):
        if outDir is None:
            outDir = self.param.cfgDir

        # get CA certificate and private key
        caCert, caKey = self._loadCertAndKey(self.param.caCertFile, self.param.caPrivkeyFile)

        # generate certificate and private key
        k = crypto.PKey()
        k.generate_key(crypto.TYPE_RSA, 1024)

        cert = crypto.X509()
        cert.get_subject().CN = hostname
        cert.set_serial_number(random.randint(0, 65535))
        cert.gmtime_adj_notBefore(0)
        cert.gmtime_adj_notAfter(36500 * 24 * 3600)
        cert.set_issuer(caCert.get_subject())
        cert.set_pubkey(k)
        cert.sign(caKey, 'sha1')

        if not isExport:
            # save certificate and private key
            certFile = os.path.join(outDir, os.path.basename(self.param.certFile))
            privkeyFile = os.path.join(outDir, os.path.basename(self.param.privkeyFile))
            self._dumpCertAndKey(cert, k, certFile, privkeyFile)
        else:
            # save CA certificate, certificate and private key to a zip file for distributing
            certFileInfo = zipfile.ZipInfo(os.path.basename(self.param.certFile))
            certFileInfo.external_attr = 0o644 << 16
            privkeyFileInfo = zipfile.ZipInfo(os.path.basename(self.param.privkeyFile))
            privkeyFileInfo.external_attr = 0o600 << 16
            with zipfile.ZipFile(os.path.join(outDir, "selfnet-distribute_%s.zip" % (hostname)), "w") as zipf:
                zipf.write(self.param.caCertFile, os.path.basename(self.param.caCertFile))
                zipf.writestr(certFileInfo, crypto.dump_certificate(crypto.FILETYPE_PEM, cert))
                zipf.writestr(privkeyFileInfo, crypto.dump_privatekey(crypto.FILETYPE_PEM, k))

    def listPeers(self):
        dbusObj = dbus.SystemBus().get_object('org.fpemud.SelfNet', '/org/fpemud/SelfNet')
        peerIdList = dbusObj.GetPeerList(dbus_interface='org.fpemud.SelfNet')

        for peerId in peerIdList:
            peerObj = dbus.SystemBus().get_object('org.fpemud.SelfNet', '/org/fpemud/SelfNet/Peers/%d' % (peerId))
            peerName = peerObj.GetName(dbus_interface='org.fpemud.SelfNet.Peer')
            peerPowerState = peerObj.GetPowerState(dbus_interface='org.fpemud.SelfNet.Peer')
            print("%s:" % (peerName))
            print("\tPowerState: %s" % (peerPowerState))
            print("")

    def peerPowerOperation(self, peerName, opName):
        dbusObj = dbus.SystemBus().get_object('org.fpemud.SelfNet', '/org/fpemud/SelfNet')
        peerId = dbusObj.GetPeer(peerName, dbus_interface='org.fpemud.SelfNet')
        if peerId == -1:
            raise Exception("peer \"%s\" does not exist" % (peerName))

        peerObj = dbus.SystemBus().get_object('org.fpemud.SelfNet', '/org/fpemud/SelfNet/Peers/%d' % (peerId))
        peerObj.DoPowerOperation(opName, dbus_interface='org.fpemud.SelfNet.Peer')

    def listModules(self):
        dbusObj = dbus.SystemBus().get_object('org.fpemud.SelfNet', '/org/fpemud/SelfNet')
        for mk, mv in dbusObj.DebugGetModuleInfo(dbus_interface='org.fpemud.SelfNet').items():
            moduleState, moduleFailMessage = mv

            print("%s:" % (mk))
            print("\tState: %s" % (moduleState))
            if moduleState == "reject" or moduleState == "peer-reject":
                print("\tReject Message: %s" % (moduleFailMessage))
            elif moduleState == "except":
                print("\tTraceback Message:")
                print(SnUtil.addLinePrefix(moduleFailMessage, "\t\t"))

            print("")

    def _loadCertAndKey(self, certFile, keyFile):
        cert = None
        with open(certFile, "rt") as f:
            buf = f.read()
            cert = crypto.load_certificate(crypto.FILETYPE_PEM, buf)

        key = None
        with open(keyFile, "rt") as f:
            buf = f.read()
            key = crypto.load_privatekey(crypto.FILETYPE_PEM, buf)

        return (cert, key)

    def _dumpCertAndKey(self, cert, key, certFile, keyFile):
        with open(certFile, "wt") as f:
            buf = crypto.dump_certificate(crypto.FILETYPE_PEM, cert)
            f.write(buf)
            os.fchmod(f.fileno(), 0o644)

        with open(keyFile, "wt") as f:
            buf = crypto.dump_privatekey(crypto.FILETYPE_PEM, key)
            f.write(buf)
            os.fchmod(f.fileno(), 0o600)
