"""
Initialize colorama support.

NOTE: colorama will be initialized as soon as this module is imported for the first time, so don't
import it unless you KNOW you want colorama!

Licensed under the MIT License. For more, see the LICENSE file.

Author: Jake Hartz <jake@hartz.io>
"""

is_colorama_on_windows = False

try:
    import colorama
    colorama.init()

    if hasattr(colorama, "win32") and hasattr(colorama.win32, "winapi_test") and \
            colorama.win32.winapi_test():
        is_colorama_on_windows = True
except ImportError:
    colorama = None
