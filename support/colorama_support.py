"""
Initialize colorama support.

NOTE: colorama will be initialized as soon as this module is imported for the first time, so don't
import it unless you KNOW you want colorama!

Licensed under the MIT License. For more, see the LICENSE file.

Author: Jake Hartz <jake@hartz.io>
"""

try:
    import colorama
    colorama.init()
except ImportError:
    colorama = None
