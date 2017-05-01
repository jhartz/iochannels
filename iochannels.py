"""
IOChannels - Python library for flexible I/O in interactive CLI applications

The functionality in IOChannels is based on 2 types of classes:
- Log: handles output logging, but cannot get input from the user (think like a logfile);
- Channel: shows output to the user and can get input from the user (like using print()/input())

Both of these have methods accepting "Msg" objects to perform output.

Licensed under the MIT License. For more, see the LICENSE file.

Author: Jake Hartz <jake@hartz.io>
"""

import contextlib
import shutil
import sys
import threading
import time
from enum import Enum
from typing import Callable, Generator, List, Optional, Sized, TextIO, Tuple


DEFAULT_BAD_CHOICE_MSG = "Invalid choice: {}"
DEFAULT_EMPTY_CHOICE_MSG = "Choose one of: {}"


class Msg(Sized):
    """
    A message that can be printed using an instance of an implementation of Channel or Log.
    """

    class PartType(Enum):
        PROMPT_QUESTION = -1
        PROMPT_ANSWER = -2

        PRINT = 1
        STATUS = 2
        ERROR = 3
        ACCENT = 4
        BRIGHT = 5
        BG_HAPPY = 6
        BG_SAD = 7
        BG_MEH = 8

    PartProcessor = Callable[[PartType, str], str]

    def __init__(self, sep: str = " ", end: str = "\n") -> None:
        """
        Initialize a new message.

        :param sep: The separator between parts of the message.
        :param end: A string to use to terminate the message.
        """
        self._parts = []  # type: List[Tuple[Msg.PartType, str]]
        self._sep = sep  # type: str
        self._end = end  # type: str

    def add(self, part_type: "Msg.PartType", base: str = "", *args: object) -> "Msg":
        base = base or ""
        self._parts.append((part_type, str(base).format(*args)))
        return self

    def print(self, base: str = "", *args: object) -> "Msg":
        return self.add(Msg.PartType.PRINT, base, *args)

    def status(self, base: str, *args: object) -> "Msg":
        return self.add(Msg.PartType.STATUS, base, *args)

    def error(self, base: str, *args: object) -> "Msg":
        return self.add(Msg.PartType.ERROR, base, *args)

    def accent(self, base: str, *args: object) -> "Msg":
        return self.add(Msg.PartType.ACCENT, base, *args)

    def bright(self, base: str, *args: object) -> "Msg":
        return self.add(Msg.PartType.BRIGHT, base, *args)

    def bg_happy(self, base: str, *args: object) -> "Msg":
        return self.add(Msg.PartType.BG_HAPPY, base, *args)

    def bg_sad(self, base: str, *args: object) -> "Msg":
        return self.add(Msg.PartType.BG_SAD, base, *args)

    def bg_meh(self, base: str, *args: object) -> "Msg":
        return self.add(Msg.PartType.BG_MEH, base, *args)

    def get_string(self, part_processor: PartProcessor = None) -> str:
        """
        Transform this message into a string representation.

        :param part_processor: A function that takes in 2 arguments (part type, part string) and
            transforms it into a string representing the part. If not provided, then the parts are
            rendered without any transformations.
        :return: The result of processing all the parts with the part_processor.
        """
        if not part_processor:
            part_processor = lambda _, s: s
        return self._sep.join(part_processor(part_type, part_str)
                              for part_type, part_str in self._parts) + self._end

    def __len__(self) -> int:
        """
        Get the length of this message when viewed as just plain, unformatted characters.
        """
        return len(self.get_string())


class _HTMLTransforms:
    """Helpers for html_part_processor"""

    @staticmethod
    def _wrap_fg_color(color: str, s: str) -> str:
        return '<span style="color: {}; font-weight: bold;">{}</span>'.format(color, s)

    @staticmethod
    def _wrap_bg_color(color: str, s: str) -> str:
        return '<span style="background-color: {}; font-weight: bold;">{}</span>'.format(color, s)

    @staticmethod
    def _wrap_bold(s: str) -> str:
        return '<b>{}</b>'.format(s)

    @staticmethod
    def _wrap_italic(s: str) -> str:
        return '<i>{}</i>'.format(s)

    transforms_by_part_type = {
        Msg.PartType.PROMPT_QUESTION: lambda s: _HTMLTransforms._wrap_fg_color("#34E2E2", s),
        Msg.PartType.PROMPT_ANSWER:   lambda s: _HTMLTransforms._wrap_italic(s),

        Msg.PartType.PRINT:    lambda s: s,
        Msg.PartType.STATUS:   lambda s: _HTMLTransforms._wrap_fg_color("#8AE234", s),
        Msg.PartType.ERROR:    lambda s: _HTMLTransforms._wrap_fg_color("#EF2929", s),
        Msg.PartType.ACCENT:   lambda s: _HTMLTransforms._wrap_fg_color("#729FCF", s),
        Msg.PartType.BRIGHT:   lambda s: _HTMLTransforms._wrap_bold(s),
        Msg.PartType.BG_HAPPY: lambda s: _HTMLTransforms._wrap_bg_color("green", s),
        Msg.PartType.BG_SAD:   lambda s: _HTMLTransforms._wrap_bg_color("red", s),
        Msg.PartType.BG_MEH:   lambda s: _HTMLTransforms._wrap_bg_color("blue", s)
    }

    @staticmethod
    def escape_html(text: str) -> str:
        return text.replace("&", "&amp;").replace("\"", "&quot;").replace("'", "&apos;") \
                   .replace("<", "&lt;").replace(">", "&gt;")


def html_part_processor(part_type: Msg.PartType, part_str: str) -> str:
    """
    A part processor (see Msg::get_string) that generates HTML. It's expected that the HTML content
    will be embedded inside <pre></pre> tags.
    """
    html_part_str = _HTMLTransforms.escape_html(part_str)
    if part_type is not None:
        html_part_str = _HTMLTransforms.transforms_by_part_type[part_type](html_part_str)
    return html_part_str


class Log:
    """
    Interface for read-only I/O classes that log their output in some way.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._enabled = True
        self._closed = False
        self.open_timestamp = time.time()  # type: float
        self.close_timestamp = None  # type: Optional[float]

    def _write(self, msg: Msg) -> None:
        """
        See Log::output. This method should be overridden in subclasses to do the actual output
        operation.
        """
        raise NotImplementedError()

    def _flush(self) -> None:
        """
        See Log::flush. This method should be overridden in subclasses to flush output, if
        necessary.
        """
        pass

    def _close(self) -> None:
        """
        See Log::close. This method should be overridden in subclasses to close any open resources,
        if necessary.
        """
        pass

    def output(self, msg: Msg) -> None:
        """
        Append a message to the log.
        """
        if not self._closed:
            with self._lock:
                if not self._closed and self._enabled:
                    self._write(msg)
                    self._flush()

    def flush(self) -> None:
        """
        Flush any buffered output.
        """
        if not self._closed:
            with self._lock:
                if not self._closed:
                    self._flush()

    def close(self) -> None:
        """
        Close the log and release any resources. This cannot be reversed. Any future calls to Log
        methods will silently do nothing.
        """
        with self._lock:
            if not self._closed:
                self._closed = True
                self._flush()
                self._close()
                self.close_timestamp = time.time()

    def pause_logging(self) -> None:
        """
        Pause writing output to this log. Any future calls to Log::output will silently do nothing
        until Log::resume_logging is called to resume logging.
        """
        with self._lock:
            self._enabled = False

    def resume_logging(self) -> None:
        """
        Resume writing output to this log (if previously paused with Log::pause_logging).
        """
        with self._lock:
            self._enabled = True


class NullLog(Log):
    """
    Log implementation that doesn't do anything.
    """

    def _write(self, msg: Msg) -> None:
        pass

    def output(self, msg: Msg) -> None:
        # This is overridden so we don't bother acquiring the lock
        pass

    def flush(self) -> None:
        # This is overridden so we don't bother acquiring the lock
        pass


class MemoryLog(Log):
    """
    Log implementation that stores a log in memory.
    """

    def __init__(self, part_processor: Msg.PartProcessor = None) -> None:
        super().__init__()
        self._part_processor = part_processor
        self._content = ""

    def _write(self, msg: Msg) -> None:
        self._content += msg.get_string(self._part_processor)

    def get_content(self) -> str:
        """
        Read all the content in the log.
        """
        with self._lock:
            return self._content


class HTMLMemoryLog(MemoryLog):
    """
    MemoryLog subclass that renders the log as HTML.
    """

    def __init__(self) -> None:
        super().__init__(html_part_processor)

    def get_content(self) -> str:
        with self._lock:
            return '<pre>' + self._content + '</pre>'


class FileLog(Log):
    """
    Log implementation that logs to a file.
    """

    def __init__(self, file: TextIO, part_processor: Msg.PartProcessor = None) -> None:
        super().__init__()
        self._file = file
        self._part_processor = part_processor

    def _write(self, msg: Msg) -> None:
        self._file.write(msg.get_string(self._part_processor))

    def _flush(self) -> None:
        self._file.flush()

    def _close(self) -> None:
        self._file.close()


class HTMLFileLog(FileLog):
    """
    FileLog subclass that renders the log as HTML.
    """

    def __init__(self, file: TextIO) -> None:
        super().__init__(file, html_part_processor)
        file.write('\n\n<pre style="background-color: black; color: white;">\n')

    def _close(self) -> None:
        self._file.write('\n</pre>\n\n')
        super()._close()


class Channel:
    """
    Abstract class that provides methods to get input from the user and give output back to the
    user, following a command-line-like setting. The actual input and output operations are
    implemented in subclasses.

    By convention, subclass names end in "Channel".

    An instance of Channel can have "delegates", which are instances of Log subclasses that are
    written to whenever the original instance outputs something (or to echo back user input).
    """

    class ChannelStateError(Exception):
        """
        Exception raised when a thread tries to call a Channel method in an invalid way.
        """
        pass

    def __init__(self, *delegates: Log) -> None:
        self._delegates = set(delegates)
        self._lock = threading.Lock()
        self._cv = threading.Condition(self._lock)
        self._line = []  # type: List[threading.Thread]
        self._current_thread = None  # type: Optional[threading.Thread]
        self._closed = False

    def _out(self, msg: Msg) -> None:
        """
        See Channel::output. This method should be overridden in subclasses to do the actual output
        operation.
        """
        raise NotImplementedError()

    def _in(self, prompt_msg: Msg = None, autocomplete_choices: List[str] = None) -> Optional[str]:
        """
        See Channel::input. This method should be overridden in subclasses to do the actual input
        operation.
        """
        raise NotImplementedError()

    def _close(self) -> None:
        """
        See Channel::close. This method should be overridden in subclasses to close any open
        resources, if necessary. After this method is called, none of the other abstract methods
        will be called for the rest of the channel's lifetime.
        """
        pass

    def get_window_size(self) -> Tuple[Optional[int], Optional[int]]:
        """
        Get the size of the window that this Channel instance outputs to (if applicable). This
        method should be overridden in subclasses if possible.

        :return: A tuple of the form (columns, rows), e.g. (80, 24) for a standard old-school
            terminal window. If either dimension is unknown, it will be None.
        """
        return None, None

    @contextlib.contextmanager
    def _wait_in_line(self) -> Generator[None, None, None]:
        me = threading.current_thread()
        if me == self._current_thread:
            raise Channel.ChannelStateError(
                "The current thread already has a blocking lock on all I/O! Did you call a "
                "Channel method from within a blocking_io context? (See the Channel.blocking_io "
                "docs for more.)")
        with self._lock:
            self._line.append(me)
            self._cv.wait_for(lambda: self._line[0] == me, None)

            assert self._line.pop(0) == me
            if self._closed:
                raise Channel.ChannelStateError("Channel is already closed")
            try:
                self._current_thread = me
                yield
            finally:
                self._current_thread = None
                self._cv.notify_all()

    def add_delegate(self, *delegates: Log) -> None:
        """
        Add one or more new delegates to this channel. The new delegates will receive any future
        messages, but will not be backfilled with previous messages.
        """
        with self._wait_in_line():
            self._delegates |= set(delegates)

    def close(self) -> None:
        """
        Close any resources held by this channel (or any delegates). This should be called when the
        channel is no longer needed and will not be accessed again. Any future attempts to use the
        channel will raise an exception.
        """
        with self._wait_in_line():
            self._closed = True
            for delegate in self._delegates:
                delegate.close()
            self._close()

    def _message_delegates_nosync(self, msg: Msg) -> None:
        for delegate in self._delegates:
            delegate.output(msg)

    def _output_nosync(self, msg: Msg) -> None:
        """
        See Channel::output.
        """
        self._out(msg)
        self._message_delegates_nosync(msg)

    def _input_nosync(self, prompt: str = None,
                      autocomplete_choices: List[str] = None) -> Optional[str]:
        """
        See Channel::input.
        """
        msg = None
        if prompt is not None:
            msg = Msg(end=" ").add(Msg.PartType.PROMPT_QUESTION, prompt)
            self._message_delegates_nosync(msg)
        line = self._in(msg, autocomplete_choices)
        if line is None:
            self._message_delegates_nosync(Msg().print())
        else:
            self._message_delegates_nosync(Msg().add(Msg.PartType.PROMPT_ANSWER, line))
        return line

    def _prompt_nosync(self, prompt: str, choices: List[str], default_choice: str = None,
                       show_choices: bool = True, hidden_choices: List[str] = None,
                       bad_choice_msg: str = DEFAULT_BAD_CHOICE_MSG,
                       empty_choice_msg: str = DEFAULT_EMPTY_CHOICE_MSG) -> str:
        """
        See Channel::prompt.
        """
        our_choices = []
        user_choices = ""
        has_empty_choice = False

        for c in choices:
            if c == "":
                has_empty_choice = True
            else:
                our_choices.append(c.lower())
                if hidden_choices is None or c not in hidden_choices:
                    user_choices += c + "/"

        if has_empty_choice:
            # We add in this choice last
            user_choices += "Enter"
        else:
            # Strip trailing slash
            user_choices = user_choices[:-1]

        msg = prompt
        if show_choices:
            msg += " ({})".format(user_choices)
        msg += ":"

        while True:
            choice = self._input_nosync(msg)
            if choice is None:
                self._output_nosync(Msg().error(empty_choice_msg, user_choices))
            else:
                choice = choice.strip().lower()
                if choice == "":
                    if has_empty_choice:
                        return ""
                    elif default_choice is not None:
                        return default_choice.lower()
                    else:
                        self._output_nosync(Msg().error(empty_choice_msg, user_choices))
                elif choice in our_choices:
                    return choice
                else:
                    self._output_nosync(Msg().error(bad_choice_msg, choice))

    def output(self, msg: Msg) -> None:
        """
        Print a message to the user.
        """
        with self._wait_in_line():
            self._output_nosync(msg)

    def input(self, prompt: str = None, autocomplete_choices: List[str] = None) -> Optional[str]:
        """
        Ask the user for a line of input. It is better to specify a "prompt" here, rather than
        printing the prompt message without a trailing newline and then calling this method (the
        latter approach causes some hideous bugs in Channel implementations that use "readline"
        for input completion).

        :param prompt: The message to prompt the user with.
        :param autocomplete_choices: A list of choices to use for autocompletion (if implemented).
        :return: The text entered by the user, without a trailing newline, or None if they
            cancelled.
        """
        with self._wait_in_line():
            return self._input_nosync(prompt, autocomplete_choices)

    def prompt(self, prompt: str, choices: List[str], default_choice: str = None,
               show_choices: bool = True, hidden_choices: List[str] = None,
               bad_choice_msg: str = DEFAULT_BAD_CHOICE_MSG,
               empty_choice_msg: str = DEFAULT_EMPTY_CHOICE_MSG) -> str:
        """
        Ask the user a question, returning their choice.

        :param prompt: The message to prompt the user with.
        :param choices: The list of valid choices (possibly including "").
        :param default_choice: The default choice from choices (only used if "" is not in choices).
            For your own sanity, make this lowercase.
        :param show_choices: Whether to show the user the list of choices.
        :param hidden_choices: If show_choices is True, this can be a list of choices to hide from
            the user at the prompt.
        :param bad_choice_msg: An error message to print when the user enters an invalid choice.
            If a str.format placeholder is present (i.e. "{}"), it is replaced with the user's
            choice.
        :param empty_choice_msg: An error message to print when the user doesn't enter a choice,
            and there is no default. If a str.format placeholder is present (i.e. "{}"), it is
            replaced with the list of choices.
        :return: An element of choices chosen by the user (lowercased).
        """
        with self._wait_in_line():
            return self._prompt_nosync(prompt, choices, default_choice, show_choices,
                                       hidden_choices, bad_choice_msg, empty_choice_msg)

    @contextlib.contextmanager
    def blocking_io(self) -> Generator[Tuple[
                Callable[[Msg], None],
                Callable[[Optional[str], Optional[List[str]]], Optional[str]],
                Callable[[str, List[str], Optional[str], bool, Optional[List[str]], str, str], str]
            ], None, None]:
        """
        Block all synchronous I/O, only allowing input and output in one place. This is useful if
        you want to execute a series of I/O calls in sequence, without being interrupted.

        This function should be used with the "with" statement, like so:

            with channel.blocking_io() as (output_func, input_func, prompt_func):
                # ...

        Then, to do output, input, or prompting, use the context manager's functions. For the
        usage of these functions, see Channel::output, Channel::input, and Channel::prompt.

        WARNING: Calling the channel's normal I/O functions within the context of this function
        will raise a ChannelStateError!
        """
        with self._wait_in_line():
            yield (self._output_nosync, self._input_nosync, self._prompt_nosync)

    def output_list(self, msgs: List[Msg], prefix: str = "  ") -> None:
        """
        Print a list of messages to the user. We will try to organize them in columns, similar to
        the "ls" command. If any of the messages contains a newline character, then they ruin it
        for everyone (i.e. we won't attempt to organize the messages into columns).
        """
        if len(msgs) == 0:
            return

        use_cols = True
        for msg in msgs:
            if "\n" in msg.get_string():
                use_cols = False
                break

        num_cols, _ = self.get_window_size()
        if not use_cols or not num_cols:
            with self._wait_in_line():
                for msg in msgs:
                    self._output_nosync(msg)
                    self._output_nosync(Msg().print())
            return

        # Keep trying, until we can fit everything into "num_rows" rows, or each message is in its
        # own row
        for num_rows in range(1, len(msgs) + 1):
            cols = []
            msgs_left = msgs
            while len(msgs_left) > 0:
                cols.append(msgs_left[0:num_rows])
                msgs_left = msgs_left[num_rows:]
            col_lengths = [max(len(msg) for msg in col) for col in cols]
            total_width = sum(col_lengths) + len(cols) * len(prefix)
            if total_width < num_cols:
                break

        # Transform from column-major to row-major for printing
        with self._wait_in_line():
            for row_index in range(num_rows):
                for col_index in range(len(cols)):
                    if row_index < len(cols[col_index]):
                        msg = cols[col_index][row_index]
                        self._output_nosync(Msg(end="").print(prefix))
                        self._output_nosync(msg)
                        if len(msg) < col_lengths[col_index]:
                            self._output_nosync(
                                Msg(end="").print(" " * (col_lengths[col_index] - len(msg))))
                self._output_nosync(Msg().print())

    def print(self, base: str = "", *args: object, **kwargs: str) -> None:
        """Shortcut for output(Msg(...).print(...))"""
        self.output(Msg(**kwargs).print(base, *args))

    def print_bordered(self, base: str, *args: object,
                       type: Msg.PartType = Msg.PartType.PRINT) -> None:
        """
        Print a bordered message.
        """
        message = base.format(*args)
        cols, _ = self.get_window_size()
        lines = []
        for line in message.splitlines():
            if not cols:
                lines.append(line)
            else:
                while line:
                    lines.append(line[:cols-4])
                    line = line[cols-4:]
        max_len = max((len(line) for line in lines), default=0)
        if cols:
            cols = min(cols, max_len + 4)
        else:
            cols = max_len + 4

        available_width = cols - 4
        start_padding = (available_width - max_len) // 2
        line_width = available_width - start_padding

        msg = Msg(sep="\n")
        msg.add(type, "{}", "*" * cols)
        for line in lines:
            msg.add(type, "* {}{} *", " " * start_padding, line.ljust(line_width))
        msg.add(type, "{}", "*" * cols)
        self.output(msg)

    def status(self, base: str, *args: object, **kwargs: str) -> None:
        """Shortcut for output(Msg(...).status(...))"""
        self.output(Msg(**kwargs).status(base, *args))

    def status_bordered(self, base: str, *args: object) -> None:
        """Shortcut for print_bordered(..., STATUS)"""
        self.print_bordered(base, *args, type=Msg.PartType.STATUS)

    def error(self, base: str, *args: object, **kwargs: str) -> None:
        """Shortcut for output(Msg(...).error(...))"""
        self.output(Msg(**kwargs).error(base, *args))

    def error_bordered(self, base: str, *args: object) -> None:
        """Shortcut for print_bordered(..., ERROR)"""
        self.print_bordered(base, *args, type=Msg.PartType.ERROR)

    def accent(self, base: str, *args: object, **kwargs: str) -> None:
        """Shortcut for output(Msg(...).accent(...))"""
        self.output(Msg(**kwargs).accent(base, *args))

    def accent_bordered(self, base: str, *args: object) -> None:
        """Shortcut for print_bordered(..., ACCENT)"""
        self.print_bordered(base, *args, type=Msg.PartType.ACCENT)

    def bright(self, base: str, *args: object, **kwargs: str) -> None:
        """Shortcut for output(Msg(...).bright(...))"""
        self.output(Msg(**kwargs).bright(base, *args))

    def bright_bordered(self, base: str, *args: object) -> None:
        """Shortcut for print_bordered(..., BRIGHT)"""
        self.print_bordered(base, *args, type=Msg.PartType.BRIGHT)

    def bg_happy(self, base: str, *args: object, **kwargs: str) -> None:
        """Shortcut for output(Msg(...).bg_happy(...))"""
        self.output(Msg(**kwargs).bg_happy(base, *args))

    def bg_sad(self, base: str, *args: object, **kwargs: str) -> None:
        """Shortcut for output(Msg(...).bg_sad(...))"""
        self.output(Msg(**kwargs).bg_sad(base, *args))

    def bg_meh(self, base: str, *args: object, **kwargs: str) -> None:
        """Shortcut for output(Msg(...).bg_meh(...))"""
        self.output(Msg(**kwargs).bg_meh(base, *args))


class CLIChannel(Channel):
    """
    A Channel implementation that reads from stdin and writes to stdout, optionally using
    "readline" for autocompletion if available.
    """

    def __init__(self, *delegates: Log, use_readline: bool = True) -> None:
        super().__init__(*delegates)

        if use_readline:
            from support import readline_support
            self._readline_completer = readline_support.global_readline_completer
        else:
            self._readline_completer = None

    def _set_options(self, options: Optional[List[str]]) -> None:
        if self._readline_completer:
            self._readline_completer.set_options(options)

    def _out(self, msg: Msg) -> None:
        print(self._msg_to_string(msg), end="")
        sys.stdout.flush()

    def _in(self, prompt_msg: Msg = None, autocomplete_choices: List[str] = None) -> Optional[str]:
        if autocomplete_choices is not None:
            self._set_options(autocomplete_choices)

        line = None  # type: Optional[str]
        try:
            if prompt_msg:
                line = input(self._msg_to_string(prompt_msg))
            else:
                line = input()
        except EOFError:
            print()

        self._set_options(None)
        return line

    def _msg_to_string(self, msg: Msg) -> str:
        return msg.get_string()

    def get_window_size(self) -> Tuple[Optional[int], Optional[int]]:
        return shutil.get_terminal_size()


class ColorCLIChannel(CLIChannel):
    """
    A subclass of CLIChannel that prints messages in color.
    """

    def _wrap_bright(self, s: str) -> str:
        return "{}{}{}".format(self._colorama.Style.BRIGHT, s, self._colorama.Style.NORMAL)

    def _wrap_fg_color(self, color: str, s: str) -> str:
        return "{}{}{}".format(getattr(self._colorama.Fore, color),
                               self._wrap_bright(s),
                               self._colorama.Fore.RESET)

    def _wrap_bg_color(self, color: str, s: str) -> str:
        return "{}{}{}".format(getattr(self._colorama.Back, color),
                               self._wrap_fg_color("WHITE", s),
                               self._colorama.Back.RESET)

    def __init__(self, *delegates: Log, use_readline: bool = True,
                 application_name_for_error: str = None) -> None:
        super().__init__(*delegates, use_readline=use_readline)

        from support import colorama_support
        self._colorama = colorama_support.colorama

        if self._colorama:
            self._transforms_by_part_type = {
                Msg.PartType.PROMPT_QUESTION: lambda s: self._wrap_fg_color("CYAN", s),
                Msg.PartType.PROMPT_ANSWER:   lambda s: s,

                Msg.PartType.PRINT:    lambda s: s,
                Msg.PartType.STATUS:   lambda s: self._wrap_fg_color("GREEN", s),
                Msg.PartType.ERROR:    lambda s: self._wrap_fg_color("RED", s),
                Msg.PartType.ACCENT:   lambda s: self._wrap_fg_color("BLUE", s),
                Msg.PartType.BRIGHT:   lambda s: self._wrap_bright(s),
                Msg.PartType.BG_HAPPY: lambda s: self._wrap_bg_color("GREEN", s),
                Msg.PartType.BG_SAD:   lambda s: self._wrap_bg_color("RED", s),
                Msg.PartType.BG_MEH:   lambda s: self._wrap_bg_color("BLUE", s)
            }
        else:
            # The default functionality will just fall back to boring ol' black-and-white
            self.print()
            self.error("==> Colorama module not found!")
            self.error("==> {} will be in boring ol' black-and-white",
                       application_name_for_error or "Output")
            self.print()

    def _msg_to_string(self, msg: Msg) -> str:
        if self._colorama is None:
            return super()._msg_to_string(msg)

        return msg.get_string(lambda part_type, part_str:
                              self._transforms_by_part_type[part_type](part_str))
