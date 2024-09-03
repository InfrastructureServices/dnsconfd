#!/bin/bash

function spincheck() {
  code=1
  time=0
  while [ $code != 0 ] && bc -l <<< "$time < $3" | grep 1; do
   sleep "$2"
   time=$(bc -l <<< "scale=2; $time+$2")
   eval "$1"
   code=$?
  done
}
