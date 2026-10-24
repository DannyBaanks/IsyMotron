"""Trusted guest bootstrap. Executed by system Python inside the provider mount namespace."""
import ctypes
import json
import os
import resource
import runpy
import sys


def main():
    request = json.load(sys.stdin)
    policy = request['security']
    resource.setrlimit(resource.RLIMIT_AS, (policy['memory_mb'] * 1024**2,) * 2)
    resource.setrlimit(resource.RLIMIT_CPU, (policy['timeout_s'],) * 2)
    resource.setrlimit(resource.RLIMIT_FSIZE, (policy['max_output_bytes'],) * 2)
    resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    # Kernel filter is installed before guest imports. Guest Python cannot
    # remove it or turn a trapped syscall into a successful operation.
    lib = ctypes.CDLL('libseccomp.so.2')
    lib.seccomp_init.argtypes = [ctypes.c_uint32]; lib.seccomp_init.restype = ctypes.c_void_p
    lib.seccomp_rule_add.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_int, ctypes.c_uint]
    lib.seccomp_load.argtypes = [ctypes.c_void_p]
    lib.seccomp_release.argtypes = [ctypes.c_void_p]
    lib.seccomp_syscall_resolve_name.argtypes = [ctypes.c_char_p]
    ctx = lib.seccomp_init(0x7fff0000)  # ALLOW, with explicit kernel-denied effects.
    if not ctx: raise RuntimeError('seccomp unavailable')
    try:
        for name in ('socket', 'connect', 'bind', 'listen', 'accept', 'accept4',
                     'clone', 'clone3', 'fork', 'vfork', 'execve', 'execveat',
                     'ptrace', 'mount', 'umount2', 'unshare', 'setns', 'bpf',
                     'process_vm_writev', 'kill', 'tkill', 'tgkill',
                     'fallocate', 'ioctl'):
            number = lib.seccomp_syscall_resolve_name(name.encode())
            # Python probes text streams with TCGETS; refuse ioctl with
            # EPERM so a normal isatty probe can fall back to a plain file.
            action = 0x00050001 if name == 'ioctl' else 0x00030000
            if number >= 0 and lib.seccomp_rule_add(ctx, action, number, 0) != 0:
                raise RuntimeError('cannot install required control')  # TRAP
        if lib.seccomp_load(ctx) != 0: raise RuntimeError('cannot load controls')
    finally:
        lib.seccomp_release(ctx)
    os.chdir('/work')
    sys.path.insert(0, '/tool')
    namespace = runpy.run_path('/tool/' + request['entrypoint'])
    result = namespace['run'](request['inputs'])
    print(json.dumps(result, allow_nan=False, ensure_ascii=False))


if __name__ == '__main__': main()
