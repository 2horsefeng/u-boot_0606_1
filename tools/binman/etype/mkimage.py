# SPDX-License-Identifier: GPL-2.0+
# Copyright (c) 2016 Google, Inc
# Written by Simon Glass <sjg@chromium.org>
#
# Entry-type module for producing an image using mkimage
#

from collections import OrderedDict

from binman.entry import Entry
from dtoc import fdt_util
from patman import tools

class Entry_mkimage(Entry):
    """Binary produced by mkimage

    Properties / Entry arguments:
        - args: Arguments to pass
        - data-to-imagename: Indicates that the -d data should be passed in as
          the image name also (-n)

    The data passed to mkimage via the -d flag is collected from subnodes of the
    mkimage node, e.g.::

        mkimage {
            args = "-n test -T imximage";

            u-boot-spl {
            };
        };

    This calls mkimage to create an imximage with `u-boot-spl.bin` as the data
    file, with mkimage being called like this::

        mkimage -d <data_file> -n test -T imximage <output_file>

    The output from mkimage then becomes part of the image produced by
    binman. If you need to put multiple things in the data file, you can use
    a section, or just multiple subnodes like this::

        mkimage {
            args = "-n test -T imximage";

            u-boot-spl {
            };

            u-boot-tpl {
            };
        };

    Note that binman places the contents (here SPL and TPL) into a single file
    and passes that to mkimage using the -d option.

    To use CONFIG options in the arguments, use a string list instead, as in
    this example which also produces four arguments::

        mkimage {
            args = "-n", CONFIG_SYS_SOC, "-T imximage";

            u-boot-spl {
            };
        };

    If you need to pass the input data in with the -n argument as well, then use
    the 'data-to-imagename' property::

        mkimage {
            args = "-T imximage";
            data-to-imagename;

            u-boot-spl {
            };
        };

    That will pass the data to mkimage both as the data file (with -d) and as
    the image name (with -n). In both cases, a filename is passed as the
    argument, with the actual data being in that file.

    If need to pass different data in with -n, then use an `imagename` subnode::

        mkimage {
            args = "-T imximage";

            imagename {
                blob {
                    filename = "spl/u-boot-spl.cfgout"
                };
            };

            u-boot-spl {
            };
        };

    This will pass in u-boot-spl as the input data and the .cfgout file as the
    -n data.
    """
    def __init__(self, section, etype, node):
        super().__init__(section, etype, node)
        self._mkimage_entries = OrderedDict()
        self._imagename = None
        self.align_default = None

    def ReadNode(self):
        super().ReadNode()
        self._args = fdt_util.GetArgs(self._node, 'args')
        self._data_to_imagename = fdt_util.GetBool(self._node,
                                                   'data-to-imagename')
        if self._data_to_imagename and self._node.FindNode('imagename'):
            self.Raise('Cannot use both imagename node and data-to-imagename')
        self.ReadEntries()

    def ReadEntries(self):
        """Read the subnodes to find out what should go in this image"""
        for node in self._node.subnodes:
            entry = Entry.Create(self, node)
            entry.ReadNode()
            if entry.name == 'imagename':
                self._imagename = entry
            else:
                self._mkimage_entries[entry.name] = entry

    def ObtainContents(self):
        # Use a non-zero size for any fake files to keep mkimage happy
        # Note that testMkimageImagename() relies on this 'mkimage' parameter
        data, input_fname, uniq = self.collect_contents_to_file(
            self._mkimage_entries.values(), 'mkimage', 1024)
        if data is None:
            return False
        if self._imagename:
            image_data, imagename_fname, _ = self.collect_contents_to_file(
                [self._imagename], 'mkimage-n', 1024)
            if image_data is None:
                return False
        output_fname = tools.get_output_filename('mkimage-out.%s' % uniq)

        args = ['-d', input_fname]
        if self._data_to_imagename:
            args += ['-n', input_fname]
        elif self._imagename:
            args += ['-n', imagename_fname]
        args += self._args + [output_fname]
        if self.mkimage.run_cmd(*args) is not None:
            self.SetContents(tools.read_file(output_fname))
        else:
            # Bintool is missing; just use the input data as the output
            self.record_missing_bintool(self.mkimage)
            self.SetContents(data)

        return True

    def GetEntries(self):
        # Make a copy so we don't change the original
        entries = OrderedDict(self._mkimage_entries)
        if self._imagename:
            entries['imagename'] = self._imagename
        return entries

    def SetAllowMissing(self, allow_missing):
        """Set whether a section allows missing external blobs

        Args:
            allow_missing: True if allowed, False if not allowed
        """
        self.allow_missing = allow_missing
        for entry in self._mkimage_entries.values():
            entry.SetAllowMissing(allow_missing)
        if self._imagename:
            self._imagename.SetAllowMissing(allow_missing)

    def SetAllowFakeBlob(self, allow_fake):
        """Set whether the sub nodes allows to create a fake blob

        Args:
            allow_fake: True if allowed, False if not allowed
        """
        for entry in self._mkimage_entries.values():
            entry.SetAllowFakeBlob(allow_fake)
        if self._imagename:
            self._imagename.SetAllowFakeBlob(allow_fake)

    def CheckFakedBlobs(self, faked_blobs_list):
        """Check if any entries in this section have faked external blobs

        If there are faked blobs, the entries are added to the list

        Args:
            faked_blobs_list: List of Entry objects to be added to
        """
        for entry in self._mkimage_entries.values():
            entry.CheckFakedBlobs(faked_blobs_list)
        if self._imagename:
            self._imagename.CheckFakedBlobs(faked_blobs_list)

    def AddBintools(self, btools):
        super().AddBintools(btools)
        self.mkimage = self.AddBintool(btools, 'mkimage')
