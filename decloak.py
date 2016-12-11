#!/usr/bin/env python2.7

import sys

def decloak(ip, channel, user):
	ip_ranges = tuple(tuple(ip_range * 32 + octet for octet in range(32)) for ip_range in range(8))

	for next in range(0, 4-len(ip.split('.'))):
		ip += '.*'

	print '/mode {channel} +m'.format(channel=channel)

	for ip_range in ip_ranges:
		for possible in ip_range:
			print '/mode +q {ip}'.format(ip=ip.replace('x', str(possible)))

		print '/msg chanserv unquiet {channel} {user}'.format(channel=channel, user=user)
		print '/msg chanserv clear {channel} bans q'.format(channel=channel)

	print '/mode {channel} -m'.format(channel=channel)

if __name__ == '__main__':
	decloak(sys.argv[1], sys.argv[2], sys.argv[3])