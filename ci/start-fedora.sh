#!/usr/bin/env bash

# shell script to start up continunous integration exist instance
cd ${FCREPO_FOLDER}
nohup ./start.sh &
sleep 30
cat nohup.out
curl http://127.0.0.1:8080/fedora
