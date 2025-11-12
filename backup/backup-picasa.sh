#!/bin/sh

while true; do
	# Echo date so we know when the loop started
	date

	# We cd each time around incase we are on an external HD and it has been
	# remounted.
	cd "$1" || exit

	# Make sure the backups directory exists, this to prevent us syncing to the
	# local HD if the external HD goes away (such as power failure).
	if [ ! -e .picasa ]; then
		echo "No backup dir found :("
		sleep 5
		continue
	fi

	# Do the actual download
	~/rcfiles/backup/backup-picasa.py

	sleep 3600
done
