"""
Initialize readline support.

NOTE: readline will be initialized as soon as this module is imported for the first time, so don't
import it unless you KNOW you want readline!

Licensed under the MIT License. For more, see the LICENSE file.

Author: Jake Hartz <jake@hartz.io>
"""

import atexit
from typing import Callable, List, Optional, cast


class InputCompleter:
    """
    Class used to handle autocomplete on an input via the readline module.
    Inspired by rlcompleter from the python standard library.
    """

    def __init__(self) -> None:
        self.options = None  # type: Optional[List[str]]
        self.matches = None  # type: Optional[List[str]]

    def set_options(self, options: Optional[List[str]]) -> None:
        self.options = options
        self.matches = None

    def __call__(self, text: str, state: int) -> Optional[str]:
        """
        Get the next possible completion for "text".

        :param text: The text that the user has entered so far.
        :param state: The index of the item in the results list.
        :return: The item matched by text and state, or None.
        """
        if self.options is None:
            # readline not currently turned on; maybe the user actually wants a tab character
            if state == 0:
                _readline.insert_text("\t")
                _readline.redisplay()
                return ""

        if not text.strip():
            return None

        if state == 0 or self.matches is None:
            self.matches = [s for s in self.options if s and s.startswith(text)]

        try:
            return self.matches[state]
        except IndexError:
            return None

try:
    import readline as _readline
    global_readline_completer = InputCompleter()  # type: Optional[InputCompleter]
    _readline.set_completer(cast(Callable[[str, int], str], global_readline_completer))
    _readline.parse_and_bind("tab: complete")
    atexit.register(lambda: _readline.set_completer(None))
except ImportError:
    _readline = None
    global_readline_completer = None
