# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

import os
import sys

sys.path.insert(0, os.path.abspath("../.."))

# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information

project = "hyper2kvm"
copyright = "2026, ZyvorAI Labs Private Limited"
author = "ZyvorAI Labs Private Limited"
release = "2.0"
version = "2.0"

# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",
    "sphinx.ext.intersphinx",
]

templates_path = ["_templates"]
exclude_patterns = []

# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

html_theme = "sphinx_rtd_theme"
html_static_path = ["_static"]

# -- Options for manual page output ------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-manual-page-output

# One entry per manual page. List of tuples
# (source start file, name, description, authors, manual section).
man_pages = [
    ("index", "hyper2kvm", "hyper2kvm - VM migration toolkit", [author], 1),
    ("hyper2kvm-local", "hyper2kvm-local", "Convert local VMDK/VHD files", [author], 1),
    ("hyper2kvm-vsphere", "hyper2kvm-vsphere", "Migrate from VMware vSphere", [author], 1),
    ("hyper2kvm-hyperv", "hyper2kvm-hyperv", "Migrate from Microsoft Hyper-V", [author], 1),
    ("hyper2kvm-azure", "hyper2kvm-azure", "Migrate from Microsoft Azure", [author], 1),
    ("hyper2kvm.conf", "hyper2kvm.conf", "hyper2kvm configuration file format", [author], 5),
]

# If true, show URL addresses after external links.
man_show_urls = True

# -- Options for Texinfo output ----------------------------------------------

texinfo_documents = [
    (
        "index",
        "hyper2kvm",
        "hyper2kvm Documentation",
        author,
        "hyper2kvm",
        "Production-grade hypervisor to KVM migration toolkit.",
        "Miscellaneous",
    ),
]

# -- Extension configuration -------------------------------------------------

# Napoleon settings
napoleon_google_docstring = True
napoleon_numpy_docstring = True
napoleon_include_init_with_doc = False
napoleon_include_private_with_doc = False
napoleon_include_special_with_doc = True
napoleon_use_admonition_for_examples = False
napoleon_use_admonition_for_notes = False
napoleon_use_admonition_for_references = False
napoleon_use_ivar = False
napoleon_use_param = True
napoleon_use_rtype = True
napoleon_preprocess_types = False
napoleon_type_aliases = None
napoleon_attr_annotations = True

# Intersphinx mapping
intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
}
