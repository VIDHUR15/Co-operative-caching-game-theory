"""
Makes the project root importable from tests/, so
`import topology`, `import game_theory`, etc. work without
needing to install the project as a package.
"""

import os
import sys

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
