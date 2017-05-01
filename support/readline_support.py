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

    This class can be set to have either a list of autocomplete options, or only a single
    autocomplete option.

    There's a difference between using "set_option" with a list with only one option, and using
    "set_single_option". If the user hasn't entered anything yet, and hits TAB:
    - If a list was set using "set_options", then no match is returned.
    - If a single option was set using "set_single_option", then that option is returned.
    Note that having a single option be returned when the user hasn't entered any text can cause
    odd issues if the user enters some text, then a space, then hits TAB.
    """

    def __init__(self) -> None:
        self.options = None  # type: Optional[List[str]]
        self.matches = None  # type: Optional[List[str]]

        self.single_option = None  # type: Optional[str]

    def set_options(self, options: Optional[List[str]]) -> None:
        self.options = options
        self.matches = None

        self.single_option = None

    def set_single_option(self, option: str) -> None:
        self.options = None
        self.matches = None

        self.single_option = option

    def __call__(self, text: str, state: int) -> Optional[str]:
        """
        Get the next possible completion for "text".

        :param text: The text that the user has entered so far.
        :param state: The index of the item in the results list.
        :return: The item matched by text and state, or None.
        """
        if self.options is not None:
            return self._get_option(text, state)
        elif self.single_option is not None:
            return self._get_single_option(text, state)
        else:
            # readline not currently turned on; maybe the user actually wants a tab character
            if state == 0:
                _readline.insert_text("\t")
                _readline.redisplay()
                return ""

    def _get_option(self, text: str, state: int) -> Optional[str]:
        if not text.strip():
            return None

        if state == 0 or self.matches is None:
            self.matches = [s for s in self.options if s and s.startswith(text)]

        try:
            return self.matches[state]
        except IndexError:
            return None

    def _get_single_option(self, text: str, state: int) -> Optional[str]:
        if state == 0 and self.single_option.startswith(text):
            return self.single_option
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
