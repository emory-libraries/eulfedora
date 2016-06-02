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


----

validate-checksums
------------------

**validate-checksums** is a command line utility script intended for
regularly, periodically checking that datastream checksums are valid for
content stored in a Fedora Commons repository.

When a fixity check is completed, the objects will be updated with a
RELS-EXT property indicating the date of the last fixity check, so that
objects can be checked again after a specified period.

The default logic is to find and process all objects without any fixity
check date in the RELS-EXT (prioritizing objects with the oldest modification
dates first, since these are likely to be most at risk), and then to find
any objects whose last fixity check was before a specified window (e.g., 30 days).

Because the script needs to run as a privileged fedora user (in order to access
and make minor updates to all content), if you are configuring it to run as
a cron job or similar, it is recommended to use the options to generate a config
file and then load options from that config file when running under cron.

For example, to generate a config file::

  validate-checksums --generate-config /path/to/config.txt --fedora-password=#####

Any arguments passed via the command line will be set in the generated
config file; you must pass the password so it can be encrypted in the config
file and decrypted for use.

To update a config file from an earlier version of the script::

  validate-checksums --config /old/config.txt --generate-config /new/config.txt

This will preserve all settings in the old config file and generate a new config
file with all new settings that are available in the script.

To configure the script to send an email report when invalid or missing checksums
are found or when there are any errors saving objects, you can specify email
addresses, a from email address, and an smtp server via the command line or a
config file.


----

repo-cp
-------

**repo-cp** is a command line wrapper around
:meth:`eulfedora.syncutil.sync_object` for synchronizing objects
between Fedora repositories.

To use it, you must make a config file with the connection information
for repositories you want to copy from or into.  The config file
should contain two or more repository definitions, each structured like
this::

    [qa-fedora]
    allow_overwrite = yes
    fedora_root = https://my.fedora.server.edu:8443/fedora
    fedora_user = syncer
    fedora_password = titanic

By default the script looks for this at **$HOME/.repocpcfg**, but you
can specify an alternate path as a command line parameter.

Example use::

  repo-cp qa-fedora dev-fedora pid:1 pid:2 pid:3

By default, the script uses the Fedora **migrate** export, which requires
that your destination repository have access to pull datastream content
by URL.  If this is not the case, or if you run into checksum mismatch
errors, you should try the archive export.  This may take longer, especially
for objects with large binary datastreams since the Fedora archive export
includes base64 encoded datastream content.  Example use with optional
progress bar to show status::

  repo-cp qa-fedora dev-fedora pid:1 pid:2 pid:3 --archive --progress

This script includes a custom sync mode of `archive-xml` intended to
support copying large objects which fail due to checksum errors on
xml datastreams when copied via migrate exports.  This mode uses
the Fedora archive export, but generates a content location URL
for all content other than managed datastreams with a mimetype of text/xml.
There is additionally a `--requires-auth` flag, only used in this mode,
which adds the source Fedora credentials to the content location URL, in
order to allow retrieving content that would otherwise be restricted.  This
option should **NOT** be used to send content to a repository you do not
control or with credentials that you care about.

(Experimental): repo-cp now supports export to and import from a file
directory, nicknamed here an "airlock".  Airlocks do not require
configuration; simplify specify a directory name as your source
or target repository.  As long as your source or target is not in your
config file and is an existing directory, it will be treated as
a path where objects should be imported or exported as xml files.

  repo-cp qa-fedora dev-fedora path/to/airlock pid:1 pid:2 pid:3 --archive --progress

.. Note::

  Airlock functionality currently does not support the allow overwrite
  option available in the config.

'''
