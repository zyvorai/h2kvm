# Makefile for Sphinx documentation

# You can set these variables from the command line, and also
# from the environment for the first two.
SPHINXOPTS    ?=
SPHINXBUILD   ?= sphinx-build
SOURCEDIR     = source
BUILDDIR      = build

# Put it first so that "make" without argument is like "make help".
help:
	@$(SPHINXBUILD) -M help "$(SOURCEDIR)" "$(BUILDDIR)" $(SPHINXOPTS) $(O)

.PHONY: help Makefile

# Catch-all target: route all unknown targets to Sphinx using the new
# "make mode" option.  $(O) is meant as a shortcut for $(SPHINXOPTS).
%: Makefile
	@$(SPHINXBUILD) -M $@ "$(SOURCEDIR)" "$(BUILDDIR)" $(SPHINXOPTS) $(O)

# Custom targets
man:
	@$(SPHINXBUILD) -b man "$(SOURCEDIR)" "$(BUILDDIR)/man" $(SPHINXOPTS) $(O)
	@echo
	@echo "Build finished. The manual pages are in $(BUILDDIR)/man."

clean:
	rm -rf $(BUILDDIR)

install:
	install -d $(DESTDIR)/usr/share/man/man1
	install -d $(DESTDIR)/usr/share/man/man5
	install -m 644 $(BUILDDIR)/man/hyper2kvm.1 $(DESTDIR)/usr/share/man/man1/
	install -m 644 $(BUILDDIR)/man/hyper2kvm-local.1 $(DESTDIR)/usr/share/man/man1/
	install -m 644 $(BUILDDIR)/man/hyper2kvm-vsphere.1 $(DESTDIR)/usr/share/man/man1/
	install -m 644 $(BUILDDIR)/man/hyper2kvm-hyperv.1 $(DESTDIR)/usr/share/man/man1/
	install -m 644 $(BUILDDIR)/man/hyper2kvm-azure.1 $(DESTDIR)/usr/share/man/man1/
	install -m 644 $(BUILDDIR)/man/hyper2kvm.conf.5 $(DESTDIR)/usr/share/man/man5/
	@echo "Man pages installed to $(DESTDIR)/usr/share/man"
