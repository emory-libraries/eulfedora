#!/usr/bin/env bash

# shell script to download and run fedora for testing

set -e
# Is this version of fedora already cached?
if [ -d "$FCREPO_FOLDER" ]; then
  echo "Using cached JFS Fedora instance: ${EXIST_DB_VERSION}."
  exit 0
fi

# currently branch names are not versioned, master is fedora 3.8.1
TARBALL_URL=https://github.com/emory-lits-labs/jfs/archive/master.tar.gz

mkdir -p ${FCREPO_FOLDER}
curl -L ${TARBALL_URL} | tar xz -C ${FCREPO_FOLDER} --strip-components=1

