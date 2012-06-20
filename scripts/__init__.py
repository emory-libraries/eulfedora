# file scripts/__init__.py
# 
#   Copyright 2012 Emory University Libraries
#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.

'''

fedora-checksums
----------------

**fedora-checksums** is a command line utility script to validate or
repair datastream checksums for content stored in a Fedora Commons
repository.

.. Note::

   Requires Python2.7 (due to use of :mod:`argparse`).

The script has two basic modes: **validate** and **repair**.

In **validate** mode, the script will iterate through all objects and
validate the checksum for each datastream (or optionally each version
of any versioned datastream), reporting on invalid or missing
checksums.

In **repair** mode, the script will iterate through all objects
looking for datastreams with a checksum type of ``DISABLED`` and a
checksum value of ``none``; any such datastreams will be updated in
Fedora with a new checksum type (either as specified via script
argument ``--checksum-type`` or using the Fedora configured default),
prompting Fedora to calculate and save a new checksum.

Running this script in either mode requires passing Fedora connection
information and credentials, for example::

  $ fedora-checksums validate --fedora-root=http://localhost:8080/fedora/
  	--fedora-user=fedoraAdmin --fedora-password=fedoraAdmin

If you prefer not to specify your fedora password on the command line,
specify the ``--fedora-password`` option with an empty value and you
will be prompted::

  $ fedora-checksums validate --fedora-root=http://localhost:8080/fedora/
  	--fedora-user=fedoraAdmin --fedora-password=

.. Note::

  The fedora user you specify must have permission to find objects,
  access datastream profiles and history, have permission to run the
  compareDatastreamChecksum API method (when validating), and
  permission to modify datastreams (when repairing).

If you have specific objects you wish to check or repair, you can run
the script with a list of pids.  When validating, there is also an
option to output details to a CSV file for further investigation.  For
more details, see the script usage for the appropriate mode::

  $ fedora-checksums validate --help
  $ fedora-checksums repair --help


.. Note::

  If the python package :mod:`progressbar` is available, progress will
  be displayed as objects are processed; however, :mod:`progressbar`
  is not required to run this script.

'''
