from gi.repository import GLib
from gi.repository import Gio

def on_read(source, res, user_data):
    print "on_read, %s, %s" % (source.__class__, res.__class__)

def on_incoming(service, con, source):
    print "on_incoming, %s, %s, %s" % (service.__class__, con.__class__, source.__class__)

    cert = Gio.TlsCertificate.new_from_files("/etc/selfnetd/my-cert.pem", "/etc/selfnetd/my-privkey.pem")
    con = Gio.TlsServerConnection.new(con, cert)

    con.get_input_stream().read_bytes_async(1024, GLib.PRIORITY_DEFAULT, None, on_read, None)

ss = Gio.SocketService()
ss.connect("incoming", on_incoming)
ss.add_inet_port(2107)
ss.start()

GLib.MainLoop().run()




