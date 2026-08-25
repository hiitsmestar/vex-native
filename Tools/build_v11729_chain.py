#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import sys

subprocess.run([sys.executable, 'Tools/build_v11728_chain.py'], check=True)
subprocess.run([sys.executable, 'Tools/apply_v11729_true_single_supervisor_runtime.py'], check=True)
