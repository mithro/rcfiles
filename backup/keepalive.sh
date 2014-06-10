#! /bin/sh

LASTGOOD=$(date +%s)
RESTART="echo restart"

while true; do
	# Check all the IP addresses
	for addr in 192.168.176.1 192.168.179.1 www.google.com; do
		# If the ping was successful, update the LASTGOOD time
		if ping -n -W 5 -c 3 $addr; then
			echo "Pinging $addr was successful!"
			LASTGOOD=$(date +%s)
		else
			echo "Pinging $addr failed!"
		fi
	done

	DELTA=$(( $(date +%s) - $LASTGOOD ))
	if [  $DELTA -gt 600 ]; then
		echo "Doing a restart, as it's been too long since good!"
		$RESTART
	else
		echo "Not restarting, $DELTA"
		sleep 10
	fi
done
