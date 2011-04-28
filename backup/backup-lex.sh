#!/bin/sh

while true; do
	# Echo date so we know when the loop started
	date

	# We cd each time around incase we are on an external HD and it has been
	# remounted.
	cd $1

	# Make sure the backups directory exists, this to prevent us syncing to the
	# local HD if the external HD goes away (such as power failure).
	if [ ! -e backups ]; then
		echo "No backup dir found :("
		sleep 5
		continue
	fi

	# Do the actual rsync
	#  * We use port 2222 so that we don't get the normal SSH interactive
	#    priority.
	#  * We exclude *.tmp files which are created when the backup is in progress.
	#  * We use blowfish encryption so we use less CPU time
	#  * We login as rsync as it's a read-only user.
	rsync --progress --exclude \*.tmp -av --rsh="ssh -p 2222 -c blowfish" rsync@lex.mithis.com:/backups .

	sleep 3600
done
