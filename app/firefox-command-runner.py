#!/usr/bin/env python3

import sys
import os
import json
import struct
import subprocess
import tempfile
# a simple POSIX/Unix - only extension ;
# use something like multiprocessing to make it portable
import signal as S
import time
import select
import errno as E
import traceback as tb

# -------------------------------------------------------------------------
# settings

# replace teh last '.' for 'Downloads' or whatever
HOMEDIR = os.path.expanduser('~') 
DOWNLOADS = os.path.join( HOMEDIR, '.' )
YOUTUBEDLPATH = "/opt/homebrew/bin/youtube-dl"
WAIT_PERIOD = 1 # select() timeout, seconds



# -------------------------------------------------------------------------
# logging ( nb: better use syslog for this )

LOGFILE = os.path.join( HOMEDIR, 'firefox-command-runner.log' )

with open(LOGFILE, 'w') as L:
    print("initial check", file=L)
    print("SIGPIPE wrapper installed at %s" % ( time.strftime('%F %T'), ), file=L)


def _log(fmt, *args):
    with open(LOGFILE, 'a') as L:
        print(fmt % args, file=L)


# -------------------------------------------------------------------------
# helpers
def getMessage():
    rawLength = sys.stdin.buffer.read(4)
    if len(rawLength) == 0:
        sys.exit(0)
    messageLength = struct.unpack('@I', rawLength)[0]
    message = sys.stdin.buffer.read(messageLength).decode('utf-8')
    return json.loads(message)

# Encode a message for transmission,
# given its content.
def encodeMessage(messageContent):
    encodedContent = json.dumps(messageContent).encode('utf-8')
    encodedLength = struct.pack('@I', len(encodedContent))
    return {'length': encodedLength, 'content': encodedContent}

# Send an encoded message to stdout
def sendMessage(encodedMessage):
    sys.stdout.buffer.write(encodedMessage['length'])
    sys.stdout.buffer.write(encodedMessage['content'])
    sys.stdout.buffer.flush()

# -------------------------------------------------------------------------
# cookie handling code

# thanks @Lennon Hill for the cookie management code (see https://github.com/lennonhill/cookies-txt)
cookie_header = \
    '# Netscape HTTP Cookie File\n' + \
    '# https://curl.haxx.se/rfc/cookie_spec.html\n' + \
    '# This is a generated file! Do not edit.\n\n';

def makeCookieJar(cookies):
    with tempfile.NamedTemporaryFile(mode='w+t', suffix=".txt", delete=False) as my_jar:
        my_jar.write(cookie_header)
        my_jar.write(''.join(cookies))
        return my_jar.name


# -------------------------------------------------------------------------
# main loop

tasks = {} # { pid: (my_jar, url) }

while True:
    try:
        r_, _, _ = select.select([sys.stdin], [], [], WAIT_PERIOD)
        if r_:
            my_jar = None
            encodedMessage = getMessage()
            if not encodedMessage:
                continue
            receivedMessage = json.loads(encodedMessage) # if this fails, we try it again
            url = receivedMessage['url']
            use_cookies = bool('cookies' in receivedMessage and receivedMessage['cookies'])

            sendMessage(encodeMessage('Starting Download: ' + url))
            try:
                command_vec = [YOUTUBEDLPATH]
                config_path = os.path.abspath(os.path.join(os.pardir, 'config'))

                if os.path.isfile(config_path):
                    command_vec += ['--config-location', config_path]

                if use_cookies:
                    my_jar = makeCookieJar(receivedMessage['cookies'])
                    command_vec += ['--cookies', my_jar]

                command_vec.append(url)
                sendMessage(encodeMessage(str(command_vec)))
                pid = os.fork()
                if 0 == pid :
                    try:
                        subprocess.check_output(command_vec, cwd=DOWNLOADS, stderr=subprocess.STDOUT)
                    except subprocess.CalledProcessError as cpe:
                        _log(str(cpe.output))
                    break
                else:
                    tasks[ pid ] = ( my_jar, url)
                    _log("[%s]: %r", pid, url)
                    _log(str(tasks.keys()))
            # todo: review and most likely clear this internal try .. except block
            except Exception as err:
                _log(str(err))
                sendMessage(encodeMessage('Error Running: ' + str(command_vec) + ': ' + str(err)))

        if list(tasks.keys()):
            while True:
                try:
                    pid, status = os.waitpid( -1, os.WNOHANG )
                except OSError as e:
                    if e.errno == E.ECHILD:
                        break
                if 0 == pid:
                    break
                # else
                my_jar, url = tasks.pop(pid, (None, None))
                if my_jar is not None:
                    os.unlink(my_jar)
                if url is None :
                    _log('<%s>: unknown task', pid)
                elif status != 0:
                    _log('[%s]: %r : FAILED (%08Xh)', pid, url, status)
                    sendMessage(encodeMessage('Error downloading: %s (%08Xh)' % ( url, status)))
                else:
                    _log('[%s]: %r : Ok', pid, url)
                    sendMessage(encodeMessage('Finished downloading to %s : %r' % ( DOWNLOADS, url)))
    except Exception as err:
        ## _log('exc: %s', err)
        _log('exception: %s', tb.format_exc())
        sendMessage(encodeMessage('JSON error: ' + str(err)))

