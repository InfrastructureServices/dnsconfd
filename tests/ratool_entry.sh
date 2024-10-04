#!/bin/bash

/usr/bin/rad --loglevel info &
sleep 2
/usr/bin/ractl < /ratool.conf

sleep 10000000
