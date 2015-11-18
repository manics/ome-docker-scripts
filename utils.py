#!/usr/bin/env python

import argparse
from collections import defaultdict
import docker
import logging
import re
import sys


log = logging.getLogger('ome-docker-tools')


class DictObj(object):
    def __init__(self, d):
        for a, b in d.items():
            if isinstance(b, (list, tuple)):
                setattr(self, a, [
                    DictObj(x) if isinstance(x, dict) else x for x in b])
            else:
                setattr(self, a, DictObj(b) if isinstance(b, dict) else b)


cli = docker.Client(version='auto')


def get_registered_name(cont):
    """
    Gets the name used by registrator
    """
    cinfo = cli.inspect_container(cont)
    try:
        env = dict(kv.split('=', 1) for kv in cinfo['Config']['Env'])
        return env['SERVICE_NAME']
    except (TypeError, KeyError, ValueError):
        m = re.match('([\w\./-]*/)?([\w\.-]+)(:[\w\.-]+)?$', cont['Image'])
        return m.group(2)


def get_all_info():
    return [(get_registered_name(c), c['Image'])
            for c in cli.containers()]


def get_name_map():
    namemap = defaultdict(list)
    for c in cli.containers():
        namemap[get_registered_name(c)].append(c)
    return namemap


def stop_registered_name(name, rm=False, timeout=10):
    namemap = get_name_map()
    if name in namemap:
        for c in namemap[name]:
            log.info('Stopping container: %s %s', name, c['Id'])
            cli.stop(c, timeout=timeout)
            if rm:
                log.info('Removing container: %s', name)
                cli.remove_container(c, v=True)
    else:
        raise Exception('No matching containers found for name: %s' % name)


def run_image(image, registered_name, command, volumes):
    if volumes is None:
        volumes = []
    # http://docker-py.readthedocs.org/en/latest/volumes/
    mounts = []
    binds = {}
    for v in volumes:
        parts = v.split(':')
        if any(len(p) == 0 for p in parts):
            raise Exception('Invalid volume specification: %s' % v)
        if len(parts) == 2:
            binds[parts[0]] = { 'bind': parts[1], 'ro': False }
        elif len(parts) == 3 and parts[2] == 'ro':
            binds[parts[0]] = { 'bind': parts[1], 'ro': True }
        else:
            raise Exception('Invalid volume specification: %s' % v)
        mounts.append(parts[1])

    hostconf = docker.utils.create_host_config(binds=binds)
    env = {'SERVICE_NAME': registered_name}
    c = cli.create_container(
        image=image,
        environment=env,
        command=command,
        volumes=mounts,
        host_config=hostconf)
    log.info('Starting container: %s', registered_name)
    cli.start(c)


def exec_registered_name(name, command, interactive):
    namemap = get_name_map()
    if name in namemap:
        if len(namemap[name]) > 1:
            raise Exception(
                'Too many matching containers found for name: %s %s' % (
                    name, namemap[name]))
        c = namemap[name][0]
        log.info('Exec container: %s %s', name, c['Id'])
        e = cli.exec_create(c, command, tty=interactive)
        response = cli.exec_start(e, tty=interactive, stream=True)
        for chunk in response:
            sys.stdout.write(chunk)
            sys.stdout.flush()
        return cli.exec_inspect(e)['ExitCode']
    else:
        raise Exception('No matching containers found for name: %s' % name)


def cmdstop(opts):
    stop_registered_name(opts.name, opts.rm)


def cmdlist(opts):
    info = get_all_info()
    for nameimage in sorted(info):
        print '%s:\t%s' % nameimage


def cmdrun(opts):
    run_image(opts.image, opts.name, opts.command, opts.volume)


def cmdexec(opts):
    return exec_registered_name(opts.name, opts.command, opts.interactive)


def parse_args():
    parser = argparse.ArgumentParser(description='OMERO docker utility')
    subp = parser.add_subparsers(help='Sub-command help')

    p_stop = subp.add_parser('stop')
    p_stop.add_argument('--rm', action='store_true', help='Delete')
    p_stop.add_argument('name', help='Registered container name')
    p_stop.set_defaults(func=cmdstop)

    p_list = subp.add_parser('list')
    p_list.set_defaults(func=cmdlist)

    p_run = subp.add_parser('run')
    p_run.add_argument('image', help='Image ID')
    p_run.add_argument('name', help='Registered container name')
    p_run.add_argument('-c', '--command', default=None, help='Command string')
    p_run.add_argument(
        '-v', '--volume', action='append',
        help='Volume mount (host:guest[:ro]), can be repeated')
    p_run.set_defaults(func=cmdrun)

    p_exec = subp.add_parser('exec')
    p_exec.add_argument(
        '-i', '--interactive', action='store_true', help='Interactive TTY')
    p_exec.add_argument('name', help='Registered container name')
    p_exec.add_argument(
        'command', nargs=argparse.REMAINDER, help='Command string')
    p_exec.set_defaults(func=cmdexec)

    opts = parser.parse_args()
    return opts


def main():
    opts = parse_args()
    r = opts.func(opts)
    if r:
        sys.exit(r)


if __name__ == '__main__':
    logging.basicConfig()
    #log.setLevel(logging.INFO)
    log.setLevel(logging.DEBUG)
    main()
#conts = cli.containers()
#cinfos = [cli.inspect_container(cid) for cid in conts]






#
