#!/usr/bin/env python3
# reachy_cli.py â€” deploy and manage the Treasure Hunt agent on Reachy Mini.
#
# Works on Windows 10/11, Linux, macOS, and Raspberry Pi OS.
# Requires OpenSSH (ssh + scp) in PATH â€” included by default on all these
# platforms. Never stores passwords; use SSH key auth (see README.md Â§2).
#
# USAGE
#   python reachy_cli.py check               # test SSH + daemon
#   python reachy_cli.py deploy              # copy agent files to robot
#   python reachy_cli.py install             # deploy + systemd auto-start (once)
#   python reachy_cli.py uninstall           # remove systemd auto-start
#   python reachy_cli.py start               # start agent on robot
#   python reachy_cli.py stop                # stop agent on robot
#   python reachy_cli.py status              # agent process + /health
#   python reachy_cli.py logs                # tail agent log
#   python reachy_cli.py shell               # interactive SSH session
#
# Defaults (SSH host, port, remote path) load from reachy_cli.config.json in
# this folder. Edit that file when the robot has a fixed IP on your LAN.
#
# GLOBAL OPTIONS (any command)
#   --host  pollen@reachy-mini.local   SSH target (default)
#   --user  pollen                     Override SSH user
#   --identity  ~/.ssh/id_ed25519      Specific key file
#   --port  22                         SSH port
#   --agent-port  7000                 HTTP port agent listens on
#   --remote-dir  /home/pollen/treasure_hunt_reachy   Deploy path on robot

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))

REMOTE_DEFAULT = 'pollen@reachy-mini.local'
REMOTE_DIR     = '/home/pollen/treasure_hunt_reachy'
AGENT_PORT     = 7000
VENV_PYTHON    = '/venvs/apps_venv/bin/python'
PID_FILE       = '{}/agent.pid'.format(REMOTE_DIR)
LOG_FILE       = '{}/agent.log'.format(REMOTE_DIR)
SERVICE_NAME   = 'treasure-hunt-reachy'
CLI_CONFIG     = os.path.join(HERE, 'reachy_cli.config.json')


def _load_cli_config():
    """Read reachy_cli.config.json for persistent SSH host / port defaults."""
    if not os.path.exists(CLI_CONFIG):
        return {}
    with open(CLI_CONFIG, encoding='utf-8-sig') as f:
        return json.load(f)


def _systemd_installed(args):
    rc, _, _ = _run_remote(
        args,
        'systemctl cat {}.service >/dev/null 2>&1'.format(SERVICE_NAME),
        capture=True)
    return rc == 0


def _systemd_unit(remote_dir):
    return """[Unit]
Description=Treasure Hunt Reachy Mini agent
After=network-online.target reachy-mini-daemon.service
Wants=network-online.target

[Service]
Type=simple
User=pollen
WorkingDirectory={d}
ExecStart={py} {d}/agent.py --config {d}/config.json
Restart=on-failure
RestartSec=5
StandardOutput=append:{log}
StandardError=append:{log}

[Install]
WantedBy=multi-user.target
""".format(d=remote_dir, py=VENV_PYTHON, log='{}/agent.log'.format(remote_dir))


def _stop_manual_agent(args):
    _run_remote(
        args,
        'kill $(cat {pid} 2>/dev/null) 2>/dev/null; rm -f {pid}'.format(
            pid=PID_FILE))


# ---------------------------------------------------------------------------
# SSH helpers
# ---------------------------------------------------------------------------

def _ssh_base(args):
    """Build the common ssh argument prefix."""
    parts = ['ssh', '-o', 'StrictHostKeyChecking=accept-new',
             '-o', 'ConnectTimeout=10']
    if args.port != 22:
        parts += ['-p', str(args.port)]
    if args.identity:
        parts += ['-i', args.identity]
    return parts


def _run_remote(args, remote_cmd, capture=False, interactive=False):
    """Run a shell command on the robot via SSH."""
    cmd = _ssh_base(args) + [args.host, remote_cmd]
    if interactive:
        return subprocess.call(cmd)
    if capture:
        result = subprocess.run(cmd, capture_output=True, text=True)
        return result.returncode, result.stdout.strip(), result.stderr.strip()
    return subprocess.call(cmd)


def _scp_to(args, local_src, remote_dst, recursive=False):
    """Copy a local path to the robot via scp."""
    cmd = ['scp', '-o', 'StrictHostKeyChecking=accept-new',
           '-o', 'ConnectTimeout=10']
    if args.port != 22:
        cmd += ['-P', str(args.port)]
    if args.identity:
        cmd += ['-i', args.identity]
    if recursive:
        cmd.append('-r')
    cmd += [local_src, '{}:{}'.format(args.host, remote_dst)]
    return subprocess.call(cmd)


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_check(args):
    print('Checking SSH connectivity ...')
    rc, out, err = _run_remote(args, 'echo OK', capture=True)
    if rc != 0:
        print('  SSH FAILED: {}'.format(err or 'no output'))
        print('  Make sure SSH keys are installed (see README.md section 2).')
        return 1
    print('  SSH  [ok]')

    print('Checking reachy-mini-daemon ...')
    rc, out, _ = _run_remote(
        args,
        'systemctl is-active reachy-mini-daemon 2>/dev/null || '
        'curl -sf http://localhost:8000/api/daemon/status | python3 -c '
        '"import sys,json; d=json.load(sys.stdin); print(d.get(\'state\',\'?\'))"',
        capture=True)
    if rc == 0 and out:
        print('  daemon [ok] - {}'.format(out))
    else:
        print('  daemon [WARN] - could not confirm. Robot may still work.')

    print('Checking Python venv ...')
    rc, out, _ = _run_remote(
        args, '{} --version 2>&1'.format(VENV_PYTHON), capture=True)
    if rc == 0:
        print('  venv   [ok] - {}'.format(out))
    else:
        print('  venv   [FAIL] - {} not found'.format(VENV_PYTHON))
        return 1

    return 0


def cmd_deploy(args):
    print('Deploying to {}:{} â€¦'.format(args.host, args.remote_dir))

    # Ensure remote directory exists
    _run_remote(args, 'mkdir -p {}'.format(args.remote_dir))

    # Files to copy from this directory
    agent_files = [
        'agent.py',
        'robot.py',
        'tracker.py',
        'config.example.json',
    ]

    # Copy individual Python/config files
    for fname in agent_files:
        src = os.path.join(HERE, fname)
        if not os.path.exists(src):
            print('  SKIP  {} (not found locally)'.format(fname))
            continue
        rc = _scp_to(args, src, '{}/{}'.format(args.remote_dir, fname))
        if rc == 0:
            print('  OK    {}'.format(fname))
        else:
            print('  FAIL  {}'.format(fname))

    # Copy audio folder
    audio_src = os.path.join(HERE, 'audio')
    if os.path.isdir(audio_src):
        rc = _scp_to(args, audio_src, args.remote_dir, recursive=True)
        print('  {} audio/'.format('OK  ' if rc == 0 else 'FAIL'))
    else:
        print('  SKIP  audio/ (run build_voice.py first)')

    # Create a default config.json if one does not exist on the robot
    rc, out, _ = _run_remote(
        args,
        'test -f {}/config.json && echo exists'.format(args.remote_dir),
        capture=True)
    if 'exists' not in out:
        _run_remote(
            args,
            'cp {}/config.example.json {}/config.json'.format(
                args.remote_dir, args.remote_dir))
        print('  Created config.json from example â€” edit it on the robot if needed.')

    print('Deploy complete.')


def cmd_start(args):
    if _systemd_installed(args):
        print('Starting {} service on {} â€¦'.format(SERVICE_NAME, args.host))
        _run_remote(args, 'sudo systemctl start {}.service'.format(SERVICE_NAME))
    else:
        _stop_manual_agent(args)
        start_cmd = (
            'cd {d} && '
            '{py} agent.py --config {d}/config.json '
            '> {log} 2>&1 & echo $! > {pid} && echo "started pid $(cat {pid})"'
        ).format(d=args.remote_dir, py=VENV_PYTHON, log=LOG_FILE, pid=PID_FILE)
        print('Starting agent on {} â€¦'.format(args.host))
        _run_remote(args, start_cmd)
    time.sleep(1.5)
    cmd_status(args)


def cmd_stop(args):
    print('Stopping agent on {} â€¦'.format(args.host))
    if _systemd_installed(args):
        rc, out, _ = _run_remote(
            args,
            'sudo systemctl stop {}.service && echo stopped || echo "not running"'.format(
                SERVICE_NAME),
            capture=True)
    else:
        rc, out, _ = _run_remote(
            args,
            'kill $(cat {pid} 2>/dev/null) 2>/dev/null && rm -f {pid} && '
            'echo stopped || echo "not running"'.format(pid=PID_FILE),
            capture=True)
    print(' ', out or '(no output)')


def cmd_status(args):
    """Print agent process/service state and /health. Exit 1 if SSH or health fails."""
    ok = True
    if _systemd_installed(args):
        rc, out, err = _run_remote(
            args,
            'systemctl is-active {}.service 2>/dev/null || echo inactive'.format(
                SERVICE_NAME),
            capture=True)
        if rc != 0 and not out:
            print('Service : SSH FAILED ({})'.format(err or 'no output'))
            return 1
        print('Service :', out or 'unknown')
    else:
        rc, out, err = _run_remote(
            args,
            'pid=$(cat {pid} 2>/dev/null); '
            'if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then '
            '  echo "running pid $pid"; '
            'else '
            '  echo "not running"; '
            'fi'.format(pid=PID_FILE),
            capture=True)
        if rc != 0 and not out:
            print('Process : SSH FAILED ({})'.format(err or 'no output'))
            return 1
        print('Process :', out)

    robot_host = args.host.split('@')[-1]
    url = 'http://{}:{}/health'.format(robot_host, args.agent_port)
    try:
        with urllib.request.urlopen(url, timeout=3) as r:
            body = json_load(r.read())
            print('Health  :', body.get('status', '?'),
                  '| robot_ready={}'.format(body.get('robot_ready', '?')))
    except urllib.error.URLError as exc:
        print('Health  : unreachable ({})'.format(exc.reason))
        ok = False
    except Exception as exc:
        print('Health  : error ({})'.format(exc))
        ok = False
    return 0 if ok else 1


def cmd_logs(args):
    if _systemd_installed(args):
        _run_remote(
            args,
            'journalctl -u {}.service -n 40 --no-pager 2>/dev/null; '
            'echo "--- agent.log ---"; tail -40 {}'.format(SERVICE_NAME, LOG_FILE))
    else:
        _run_remote(args, 'tail -80 {}'.format(LOG_FILE))


def cmd_install(args):
    """Deploy files and enable systemd auto-start on the robot (run once)."""
    print('One-time install - deploy + auto-start on boot ...')
    if cmd_check(args) != 0:
        print('Install aborted - fix SSH/daemon issues first.')
        return 1
    cmd_deploy(args)
    _stop_manual_agent(args)

    unit = _systemd_unit(args.remote_dir)
    # Write unit file via a heredoc on the robot (no local temp file needed).
    remote_write = (
        "cat <<'EOF' | sudo tee /etc/systemd/system/{}.service >/dev/null\n"
        "{}\n"
        "EOF\n"
        "sudo systemctl daemon-reload && "
        "sudo systemctl enable {}.service && "
        "sudo systemctl restart {}.service"
    ).format(SERVICE_NAME, unit.rstrip(), SERVICE_NAME, SERVICE_NAME)
    print('Installing systemd service {} â€¦'.format(SERVICE_NAME))
    rc = _run_remote(args, remote_write)
    if rc != 0:
        print('Install FAILED â€” could not install systemd unit (sudo required).')
        return rc
    time.sleep(2)
    print('Install complete â€” agent starts automatically when the robot boots.')
    cmd_status(args)
    return 0


def cmd_uninstall(args):
    """Disable systemd auto-start and remove the service unit."""
    print('Removing systemd auto-start on {} â€¦'.format(args.host))
    if _systemd_installed(args):
        _run_remote(
            args,
            'sudo systemctl disable --now {}.service; '
            'sudo rm -f /etc/systemd/system/{}.service; '
            'sudo systemctl daemon-reload'.format(SERVICE_NAME, SERVICE_NAME))
        print('Systemd service removed.')
    else:
        print('No systemd service installed â€” nothing to remove.')
    _stop_manual_agent(args)
    return 0


def cmd_shell(args):
    print('Opening interactive SSH session to {} â€” type exit to return.'.format(
        args.host))
    _run_remote(args, '', interactive=True)


# ---------------------------------------------------------------------------
# JSON helper
# ---------------------------------------------------------------------------

def json_load(data):
    if isinstance(data, (bytes, bytearray)):
        data = data.decode('utf-8', errors='replace')
    return json.loads(data)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

COMMANDS = {
    'check':     cmd_check,
    'deploy':    cmd_deploy,
    'install':   cmd_install,
    'uninstall': cmd_uninstall,
    'start':     cmd_start,
    'stop':      cmd_stop,
    'status':    cmd_status,
    'logs':      cmd_logs,
    'shell':     cmd_shell,
}


def main():
    cfg = _load_cli_config()
    parser = argparse.ArgumentParser(
        description='Manage the Treasure Hunt Reachy Mini agent over SSH',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='\n'.join(
            ['commands:'] + ['  {:<10} {}'.format(k, COMMANDS[k].__doc__ or '')
                             for k in COMMANDS]))
    parser.add_argument('command', choices=list(COMMANDS))
    parser.add_argument('--host',       default=cfg.get('host', REMOTE_DEFAULT),
                        help='SSH target (default from reachy_cli.config.json)')
    parser.add_argument('--user',       help='Override SSH user')
    parser.add_argument('--identity',   default=cfg.get('identity'),
                        help='SSH identity file (-i)')
    parser.add_argument('--port',       type=int, default=22)
    parser.add_argument('--agent-port', type=int, default=cfg.get('agent_port', AGENT_PORT),
                        dest='agent_port')
    parser.add_argument('--remote-dir', default=cfg.get('remote_dir', REMOTE_DIR),
                        dest='remote_dir')
    args = parser.parse_args()

    if args.user:
        # Rebuild host with explicit user
        hostname = args.host.split('@')[-1]
        args.host = '{}@{}'.format(args.user, hostname)

    rc = COMMANDS[args.command](args)
    if isinstance(rc, int) and rc != 0:
        sys.exit(rc)


if __name__ == '__main__':
    main()
