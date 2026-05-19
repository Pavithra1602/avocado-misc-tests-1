#!/usr/bin/env python
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
#
# See LICENSE for more details.
#
# Copyright: 2017 IBM
# Author: Harish S <harish@linux.vnet.ibm.com>
#         Basheer K<basheer@linux.vnet.ibm.com>
#

import os
import shutil
import re
from avocado import Test
from avocado.utils import process, build, memory, archive
from avocado.utils.software_manager.manager import SoftwareManager


class Memtester(Test):
    """
    1.memtester  is  an  effective  userspace  tester  for stress-testing the
      memory subsystem.  It is very effective  at  finding  intermittent  and
      non-deterministic  faults.
    2.memtester must be run with  root  privileges  to  mlock(3)  its  pages.
      Testing  memory  without locking the pages in place is mostly pointless
      and slow.

    :avocado: tags=memory,privileged
    """

    def setUp(self):
        '''
        Setup memtester
        '''
        smm = SoftwareManager()

        for pkg in ['gcc', 'make']:
            if not smm.check_installed(pkg) and not smm.install(pkg):
                self.cancel('%s is needed for the test to be run' % pkg)
        self.gcc_backup_path = None
        self.gcc_replaced = False
        try:
            gcc_version_output = process.run('gcc --version', shell=True).stdout_text
            version_match = re.search(r'gcc.*?(\d+)\.', gcc_version_output)
            if version_match:
                gcc_major_version = int(version_match.group(1))
                self.log.info(f"Detected GCC version: {gcc_major_version}")
                if gcc_major_version >= 15:
                    self.log.info("GCC version >= 15 detected, replacing with GCC-13")
                    gcc13_path = '/usr/bin/gcc-13'
                    if not os.path.exists(gcc13_path):
                        self.log.info("gcc-13 not found, attempting to install")
                        if not smm.check_installed('gcc13') and not smm.install('gcc13'):
                            if not smm.check_installed('gcc-13') and not smm.install('gcc-13'):
                                self.cancel('gcc-13 is required but could not be installed')
                        if not os.path.exists(gcc13_path):
                            self.cancel('gcc-13 package installed but binary not found at /usr/bin/gcc-13')
                    gcc_path = '/usr/bin/gcc'
                    self.gcc_backup_path = '/usr/bin/gcc.backup.memtester'
                    try:
                        shutil.copy2(gcc_path, self.gcc_backup_path)
                        self.log.info(f"Backed up {gcc_path} to {self.gcc_backup_path}")
                        shutil.copy2(gcc13_path, gcc_path)
                        self.gcc_replaced = True
                        self.log.info(f"Replaced {gcc_path} with {gcc13_path}")
                    except Exception as e:
                        self.log.error(f"Failed to replace GCC: {e}")
                        if os.path.exists(self.gcc_backup_path):
                            os.remove(self.gcc_backup_path)
                        raise
        except Exception as e:
            self.log.warning(f"Could not check GCC version: {e}")
        tarball = self.fetch_asset('memtester.zip',
                                   locations=['https://github.com/jnavila/'
                                              'memtester/archive/master.zip'],
                                   expire='7d')
        archive.extract(tarball, self.workdir)
        sourcedir = os.path.join(self.workdir, 'memtester-master')
        os.chdir(sourcedir)
        process.system('chmod 755 extra-libs.sh', shell=True, sudo=True,
                       ignore_status=True)
        build.make(sourcedir)

    def tearDown(self):
        '''
        Restore original GCC if it was replaced
        '''
        gcc_replaced = getattr(self, 'gcc_replaced', False)
        gcc_backup_path = getattr(self, 'gcc_backup_path', None)
        if gcc_replaced and gcc_backup_path:
            try:
                gcc_path = '/usr/bin/gcc'
                if os.path.exists(gcc_backup_path):
                    shutil.copy2(gcc_backup_path, gcc_path)
                    self.log.info(f"Restored original GCC from {gcc_backup_path}")
                    os.remove(gcc_backup_path)
                    self.log.info(f"Removed backup file {gcc_backup_path}")
            except Exception as e:
                self.log.error(f"Failed to restore original GCC: {e}")

    def test(self):
        '''
        Run memtester
        '''
        mem = self.params.get('memory', default=memory.meminfo.MemFree.m)
        runs = self.params.get('runs', default=1)
        phyaddr = self.params.get('physaddr', default=None)

        # Basic Memtester usecase
        if process.system("./memtester %s %s" % (mem, runs), verbose=True,
                          sudo=True,
                          ignore_status=True):
            self.fail("memtester failed for free space %s" % mem)

        if phyaddr:
            # To verify -p option if provided in the yaml file
            device = self.params.get('device', default='/dev/mem')
            if process.system("./memtester -p %s -d %s %s %s" %
                              (phyaddr, device, mem, runs), verbose=True,
                              sudo=True, ignore_status=True):
                self.fail("memtester failed for address %s" % phyaddr)
