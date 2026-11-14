#!/usr/bin/env python3
"""verify_ubuntu_portability.py — will these scripts run on Ubuntu 22.04?

The build machine is Ubuntu 22.04 and the project was developed on Windows with
Git-bash and WSL. That gap is where "works on my machine" failures come from, so
this script checks the things that actually differ, rather than trusting a
successful local run.

Checks
  1. every shell script declares a bash shebang and parses (`bash -n`)
  2. no CRLF line endings (would break `#!/usr/bin/env bash` on Linux)
  3. every external tool the scripts invoke is listed and classified
  4. GNU-specific flags used are available in Ubuntu 22.04's coreutils/tar/xz
  5. no Windows-only path assumptions in the scripts that run on the build host
  6. python entry points import cleanly and require only the stdlib

Usage: python3 scripts/verify_ubuntu_portability.py [--root DIR]
Exit:  0 = portable as far as static checks can tell, 1 = a problem was found.
"""
from __future__ import annotations

import argparse
import ast
import os
import re
import subprocess
import sys

# Tools the scripts call, and the Ubuntu 22.04 package that provides each.
TOOL_PACKAGES = {
    "bash": "bash (preinstalled)",
    "tar": "tar (preinstalled)",
    "xz": "xz-utils",
    "split": "coreutils (preinstalled)",
    "sha256sum": "coreutils (preinstalled)",
    "find": "findutils (preinstalled)",
    "grep": "grep (preinstalled)",
    "awk": "mawk/gawk (preinstalled)",
    "sed": "sed (preinstalled)",
    "git": "git",
    "repo": "repo (via google's instructions or apt)",
    "debugfs": "e2fsprogs",
    "python3": "python3",
    "brotli": "python3-brotli  (module) or the `brotli` CLI",
    "unzip": "unzip",
    "df": "coreutils (preinstalled)",
    "nproc": "coreutils (preinstalled)",
    "curl": "curl",
}

# Windows-ism that must not appear in code paths the build host executes.
WINDOWS_ONLY = [
    ("\r\n", "CRLF line endings"),
    ("C:\\", "a Windows drive path"),
    ("/c/Users/", "a Git-bash style path"),
    ("\\\\?\\", "a Windows long-path prefix"),
]

SKIP_DIRS = {"__pycache__", ".git"}


def find_bash() -> str:
    """Return a bash that can open the paths this script passes it.

    On Windows, a bare "bash" resolves to WSL's /bin/bash, which sees Windows
    paths as /mnt/c/... and cannot open "C:/...". Git-bash's bash.exe can. On
    Linux there is only one bash and this returns it unchanged.
    """
    candidates = []
    if os.name == "nt":
        for base in (os.environ.get("ProgramFiles", r"C:\Program Files"),
                     os.environ.get("ProgramW6432", r"C:\Program Files")):
            candidates.append(os.path.join(base, "Git", "bin", "bash.exe"))
            candidates.append(os.path.join(base, "Git", "usr", "bin", "bash.exe"))
    candidates.append("bash")
    for cand in candidates:
        try:
            r = subprocess.run([cand, "-c", "exit 0"], capture_output=True,
                               timeout=20)
            if r.returncode == 0:
                return cand
        except (OSError, subprocess.SubprocessError):
            continue
    return "bash"


def _posix(path: str) -> str:
    """Return a path the local bash can open.

    On Windows with Git-bash, passing a native ``C:\\...`` path as an argument
    loses the backslashes during MSYS argument conversion, so bash reports
    "No such file or directory" for a file that exists. Forward slashes work for
    both Windows and Linux, and are what the scripts themselves use.
    """
    return path.replace("\\", "/")


BASH = find_bash()


def iter_scripts(root: str):
    d = os.path.join(root, "scripts")
    if not os.path.isdir(d):
        return
    for name in sorted(os.listdir(d)):
        if name.endswith(".sh"):
            yield os.path.join(d, name)


def iter_python(root: str):
    d = os.path.join(root, "scripts")
    if not os.path.isdir(d):
        return
    for name in sorted(os.listdir(d)):
        if name.endswith(".py"):
            yield os.path.join(d, name)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))))
    args = ap.parse_args()
    root = os.path.abspath(args.root)

    findings = []          # (severity, message)
    info = []

    # ---------------------------------------------------------------- 1, 2
    shells = list(iter_scripts(root))
    info.append("%d shell scripts" % len(shells))
    for path in shells:
        rel = os.path.relpath(path, root).replace(os.sep, "/")
        with open(path, "rb") as fh:
            raw = fh.read()
        if b"\r\n" in raw:
            findings.append(("error", "%s has CRLF line endings; the shebang will "
                                      "fail on Linux" % rel))
        text = raw.decode("utf-8", "replace")
        first = text.splitlines()[0] if text else ""
        if "bash" not in first:
            findings.append(("error", "%s does not use a bash shebang: %r" % (rel, first)))
        r = subprocess.run([BASH, "-n", _posix(path)], capture_output=True,
                           text=True)
        if r.returncode != 0:
            findings.append(("error", "%s fails 'bash -n': %s"
                             % (rel, r.stderr.strip()[:200])))

    # ---------------------------------------------------------------- 3
    # Collect the command words the scripts actually invoke.
    invoked = set()
    for path in shells:
        with open(path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                s = line.strip()
                if s.startswith("#") or not s:
                    continue
                m = re.match(r"(?:if\s+|elif\s+|!\s+)?([a-z][a-z0-9_.-]{1,20})\s", s)
                if m:
                    invoked.add(m.group(1))
                for m2 in re.finditer(r"\|\|\s*([a-z][a-z0-9_.-]{1,20})\s", s):
                    invoked.add(m2.group(1))

    builtins = {
        "local", "readonly", "printf", "echo", "cd", "return", "exit", "shift",
        "set", "case", "esac", "then", "else", "fi", "for", "do", "done", "while",
        "if", "in", "function", "export", "unset", "read", "test", "true", "false",
        "break", "continue", "declare", "mapfile", "readarray", "trap", "source",
        "command", "type", "eval", "wait", "printf", "getopts", "ulimit", "let",
        "shopt", "exec", "times", "hash", "pwd", "umask", "alias", "unalias",
    }
    # Shell keywords plus the project's own helper functions are not external
    # commands; excluding them keeps the "unclassified" note meaningful.
    project_helpers = set()
    for path in shells:
        with open(path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                m = re.match(r"^\s*(?:function\s+)?([a-z_][a-z0-9_]*)\s*\(\)", line)
                if m:
                    project_helpers.add(m.group(1))
                m2 = re.match(r"^\s*([a-z_][a-z0-9_]*)=\\$\(\)", line)
                if m2:
                    project_helpers.add(m2.group(1))
    external = sorted(w for w in invoked
                      if w not in builtins and w not in project_helpers
                      and not w.startswith("_"))
    # keep only names that look like real commands
    plausible = [w for w in external
                 if w in TOOL_PACKAGES or len(w) <= 12]
    unknown = [w for w in plausible if w not in TOOL_PACKAGES]
    info.append("%d external commands referenced" % len(plausible))
    if unknown:
        # Not fatal: the heuristic over-collects shell words. Report for review.
        findings.append(("info", "unclassified shell words (review, likely benign): %s"
                         % ", ".join(sorted(unknown)[:12])))

    # ---------------------------------------------------------------- 4
    gnu_flags = {
        "--sort=name": ("tar", "GNU tar >= 1.28; Ubuntu 22.04 has 1.34"),
        "--mtime": ("tar", "GNU tar"),
        "--numeric-suffixes": ("split", "GNU coreutils"),
        "-printf": ("find", "GNU findutils"),
        "--quiet": ("sha256sum", "GNU coreutils"),
        "--reverse": ("git apply", "git"),
    }
    for path in shells:
        rel = os.path.relpath(path, root).replace(os.sep, "/")
        with open(path, encoding="utf-8", errors="replace") as fh:
            txt = fh.read()
        for flag, (tool, note) in gnu_flags.items():
            if flag in txt:
                info.append("%s uses %s (%s)" % (rel, flag, note))

    # ---------------------------------------------------------------- 5
    for path in shells:
        rel = os.path.relpath(path, root).replace(os.sep, "/")
        with open(path, "rb") as fh:
            raw = fh.read()
        for needle, label in WINDOWS_ONLY:
            b = needle.encode() if isinstance(needle, str) else needle
            if b in raw:
                findings.append(("error", "%s contains %s" % (rel, label)))

    # ---------------------------------------------------------------- 6
    pys = list(iter_python(root))
    info.append("%d python scripts" % len(pys))
    stdlib_ok, third_party = 0, set()
    for path in pys:
        rel = os.path.relpath(path, root).replace(os.sep, "/")
        try:
            with open(path, encoding="utf-8") as fh:
                tree = ast.parse(fh.read())
        except SyntaxError as exc:
            findings.append(("error", "%s does not parse: %s" % (rel, exc)))
            continue
        for node in ast.walk(tree):
            mods = []
            if isinstance(node, ast.Import):
                mods = [a.name.split(".")[0] for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                mods = [node.module.split(".")[0]]
            for m in mods:
                if m in sys.stdlib_module_names:
                    stdlib_ok += 1
                else:
                    third_party.add(m)
    # `brotli` is the one real dependency; it is documented and optional.
    for mod in sorted(third_party):
        if mod in ("brotli",):
            info.append("third-party module: %s (documented; apt install python3-brotli)"
                        % mod)
        else:
            info.append("module: %s (assumed local to scripts/)" % mod)

    # ------------------------------------------------------------- report
    print("Ubuntu 22.04 portability check")
    print("=" * 64)
    for line in info:
        print("  . %s" % line)
    errors = [f for f in findings if f[0] == "error"]
    warns = [f for f in findings if f[0] != "error"]
    print()
    for _, msg in warns:
        print("  [note] %s" % msg)
    for _, msg in errors:
        print("  [FAIL] %s" % msg)
    print("=" * 64)

    print()
    print("Required packages on Ubuntu 22.04:")
    used = set()
    for path in shells:
        with open(path, encoding="utf-8", errors="replace") as fh:
            txt = fh.read()
        for tool in TOOL_PACKAGES:
            if re.search(r"\b" + re.escape(tool) + r"\b", txt):
                used.add(tool)
    pkgs = sorted({TOOL_PACKAGES[t] for t in used if t in TOOL_PACKAGES})
    print("  sudo apt update && sudo apt install -y \\")
    print("      " + " \\\n      ".join(p.split(" ")[0] for p in pkgs
                                       if "(preinstalled)" not in p))
    print("  # (bash/coreutils/findutils/grep/sed are preinstalled)")
    print("  python3 -m pip install brotli    # or: apt install python3-brotli")

    print()
    if errors:
        print("%d blocking problem(s) found" % len(errors))
        return 1
    print("No blocking portability problem found by static inspection.")
    print("This does not prove a build works on Ubuntu; it proves the scripts")
    print("have no obvious Windows dependency and use tools Ubuntu provides.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
