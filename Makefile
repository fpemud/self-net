PACKAGE_VERSION = `/bin/fgrep GK_V= genkernel | sed "s/.*GK_V='\([^']\+\)'/\1/"`
distdir = selfnetd-$(PACKAGE_VERSION)
prefix=/usr

all:

clean:
	find . -name *.pyc | xargs rm -f

check-git-repository:
	git diff --quiet || { echo 'STOP, you have uncommitted changes in the working directory' ; false ; }
	git diff --cached --quiet || { echo 'STOP, you have uncommitted changes in the index' ; false ; }

dist: check-git-repository distclean
	mkdir "$(distdir)"
	git ls-files -z | xargs -0 cp --no-dereference --parents --target-directory="$(distdir)" 
	tar cf "$(distdir)".tar "$(distdir)"
	bzip2 -9v "$(distdir)".tar
	rm -Rf "$(distdir)"

distclean:
	rm -Rf "$(distdir)" "$(distdir)".tar "$(distdir)".tar.bz2

install:
	install -d -m 0755 "$(DESTDIR)/$(prefix)/bin"
	install -m 0755 selfnetd "$(DESTDIR)/$(prefix)/bin"

	install -d -m 0755 "$(DESTDIR)/$(prefix)/lib/selfnetd"
	cp -r src/* "$(DESTDIR)/$(prefix)/lib/selfnetd"
	find "$(DESTDIR)/$(prefix)/lib/selfnetd" -type f | xargs chmod 644
	find "$(DESTDIR)/$(prefix)/lib/selfnetd" -type d | xargs chmod 755

	install -d -m 0755 "$(DESTDIR)/etc/dbus-1/system.d"
	install -m 0644 data/org.fpemud.SelfNet.conf "$(DESTDIR)/etc/dbus-1/system.d"

	install -d -m 0755 "$(DESTDIR)/etc/selfnetd"
	cp -r cfg/* "$(DESTDIR)/etc/selfnetd"
	find "$(DESTDIR)/etc/selfnetd" -type f | xargs chmod 644
	find "$(DESTDIR)/etc/selfnetd" -type d | xargs chmod 755

#	install -d -m 0755 "$(DESTDIR)/etc/xdg/menus"
#	cp desktop/*.menu "$(DESTDIR)/etc/xdg/menus"
#	install -d -m 0755 "$(DESTDIR)/$(prefix)/lib/desktop-directories"
#	cp desktop/*.directory "$(DESTDIR)/$(prefix)/lib/desktop-directories"

uninstall:
	rm -Rf "$(DESTDIR)/$(prefix)/lib/selfnetd"

.PHONY: check-git-repository all clean dist distclean install uninstall

