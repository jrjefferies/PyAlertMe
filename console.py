#!/usr/bin/env python
# coding: utf-8

# Filename:    console.py
# Description: Communicate with Hive/AlertMe devices via a XBee
# Author:      James Saunders [james@saunders-family.net]
# Copyright:   Copyright (C) 2017 James Saunders
# License:     MIT
# Version:     0.1.3


'''
Created on Aug 2, 2015

@author: ivan
'''
import urwid
from collections import deque
import threading

class UnknownCommand(Exception):
    def __init__(self, cmd):
        Exception.__init__(self, 'Unknown command: %s' % cmd)

class Command(object):
    """
    Base class to manage commands in commander
    similar to cmd.Cmd in standard library just extend
    with do_something method to handle your commands.
    """

    def __init__(self, quit_commands=['q', 'quit', 'exit'], help_commands=['help', '?', 'h']):
        self._quit_cmd = quit_commands
        self._help_cmd = help_commands

    def __call__(self, line):
        tokens = line.split()
        cmd = tokens[0].lower()
        args = tokens[1:]
        if cmd in self._quit_cmd:
            return Commander.Exit
        elif cmd in self._help_cmd:
            return self.help(args[0] if args else None)
        elif hasattr(self, 'do_' + cmd):
            return getattr(self, 'do_' + cmd)(*args)
        else:
            raise UnknownCommand(cmd)

    def help(self, cmd=None):
        def std_help():
            qc = '|'.join(self._quit_cmd)
            hc = '|'.join(self._help_cmd)
            res = 'Type [%s] command_name to get more help about particular command\n' % hc
            res += 'Type [%s] to quit program\n' % qc
            cl = [name[3:] for name in dir(self) if name.startswith('do_') and len(name) > 3]
            res += 'Available commands: %s' % (' '.join(sorted(cl)))
            return res

        if not cmd:
            return std_help()
        else:
            try:
                fn = getattr(self, 'do_' + cmd)
                doc = fn.__doc__
                return doc or 'No documentation available for %s' % cmd
            except AttributeError:
                return std_help()


class FocusMixin(object):
    def mouse_event(self, size, event, button, x, y, focus):
        if focus and hasattr(self, '_got_focus') and self._got_focus:
            self._got_focus()
        return super(FocusMixin, self).mouse_event(size, event, button, x, y, focus)


class ListView(FocusMixin, urwid.ListBox):
    def __init__(self, model, got_focus, max_size=None):
        urwid.ListBox.__init__(self, model)
        self._got_focus = got_focus
        self.max_size = max_size
        self._lock = threading.Lock()

    def add(self, line):
        with self._lock:
            was_on_end = self.get_focus()[1] == len(self.body) - 1
            if self.max_size and len(self.body) > self.max_size:
                del self.body[0]
            self.body.append(urwid.Text(line))
            last = len(self.body) - 1
            if was_on_end:
                self.set_focus(last, 'above')


class Input(FocusMixin, urwid.Edit):
    signals = ['line_entered']

    def __init__(self, got_focus=None):
        urwid.Edit.__init__(self)
        self.history = deque(maxlen=1000)
        self._history_index = -1
        self._got_focus = got_focus

    def keypress(self, size, key):
        if key == 'enter':
            line = self.edit_text.strip()
            if line:
                urwid.emit_signal(self, 'line_entered', line)
                self.history.append(line)
            self._history_index = len(self.history)
            self.edit_text = u''
        if key == 'up':

            self._history_index -= 1
            if self._history_index < 0:
                self._history_index = 0
            else:
                self.edit_text = self.history[self._history_index]
        if key == 'down':
            self._history_index += 1
            if self._history_index >= len(self.history):
                self._history_index = len(self.history)
                self.edit_text = u''
            else:
                self.edit_text = self.history[self._history_index]
        else:
            urwid.Edit.keypress(self, size, key)


class Commander(urwid.Frame):
    """
    Simple terminal UI with command input on bottom line and display frame above
    similar to chat client etc.
    Initialize with your Command instance to execute commands and the start main loop Commander.loop().
    You can also asynchronously output messages with Commander.output('message')
    """

    class Exit(object):
        pass

    PALLETE = [('reversed', urwid.BLACK, urwid.LIGHT_GRAY),
               ('normal', urwid.LIGHT_GRAY, urwid.BLACK),
               ('error', urwid.LIGHT_RED, urwid.BLACK),
               ('green', urwid.DARK_GREEN, urwid.BLACK),
               ('blue', urwid.LIGHT_BLUE, urwid.BLACK),
               ('magenta', urwid.DARK_MAGENTA, urwid.BLACK), ]

    def __init__(self, title,
                 command_caption='Command:  (Tab to switch focus to upper frame, where you can scroll text)',
                 cmd_cb=None, max_size=1000):
        self.header = urwid.Text(title)
        self.model = urwid.SimpleListWalker([])
        self.body = ListView(self.model, lambda: self._update_focus(False), max_size=max_size)
        self.input = Input(lambda: self._update_focus(True))
        foot = urwid.Pile([urwid.AttrMap(urwid.Text(command_caption), 'reversed'),
                           urwid.AttrMap(self.input, 'normal')])
        urwid.Frame.__init__(self,
                             urwid.AttrWrap(self.body, 'normal'),
                             urwid.AttrWrap(self.header, 'reversed'),
                             foot)
        self.set_focus_path(['footer', 1])
        self._focus = True
        urwid.connect_signal(self.input, 'line_entered', self.on_line_entered)
        self._cmd = cmd_cb
        self._output_styles = [s[0] for s in self.PALLETE]
        self.eloop = None

    def loop(self, handle_mouse=False):
        self.eloop = urwid.MainLoop(self, self.PALLETE, handle_mouse=handle_mouse)
        self._eloop_thread = threading.current_thread()
        self.eloop.run()

    def on_line_entered(self, line):
        if self._cmd:
            try:
                res = self._cmd(line)
            except Exception, e:
                self.output('Error: %s' % e, 'error')
                return
            if res == Commander.Exit:
                raise urwid.ExitMainLoop()
            elif res:
                self.output(str(res))
        else:
            if line in ('q', 'quit', 'exit'):
                raise urwid.ExitMainLoop()
            else:
                self.output(line)

    def output(self, line, style=None):
        if style and style in self._output_styles:
            line = (style, line)
        self.body.add(line)
        # since output could be called asynchronously form other threads we need to refresh screen in these cases
        if self.eloop and self._eloop_thread != threading.current_thread():
            self.eloop.draw_screen()

    def _update_focus(self, focus):
        self._focus = focus

    def switch_focus(self):
        if self._focus:
            self.set_focus('body')
            self._focus = False
        else:
            self.set_focus_path(['footer', 1])
            self._focus = True

    def keypress(self, size, key):
        if key == 'tab':
            self.switch_focus()
        return urwid.Frame.keypress(self, size, key)



if __name__ == '__main__':
    class TestCmd(Command):
        def do_discovery(self, *args):
            # Discovery
            hubObj.discovery()
            return 'Discovery Started'

        def do_broadcast(self, *args):
            # Send broadcast
            message = hubObj.get_action('routing_table_request')
            hubObj.send_message(message, hubObj.BROADCAST_LONG, hubObj.BROADCAST_SHORT)
            return 'broadcast'

        def do_nodes(self, *args):
            if args[0] == 'list':
                # Construct a lise of nodes
                output = "List of Nodes: \n"

                nodes = hubObj.get_nodes()
                for id, node in nodes.iteritems():
                    output += str(id) + ". " + node['Type'] + " [" + node['Name'] + "] (" + Base.pretty_mac(node['AddressLong']) + ")\n"

                return output

            if args[0].isdigit():
                node_id = int(args[0])

                if args[1] == "rename":
                    # Concatenate all following params
                    name = " ".join(map(lambda s: '"%s"' % s if ' ' in s else s, args[2:]))
                    if name == '':
                        raise Exception('Name too short!')

                    hubObj.set_node_name(node_id, name)
                    return 'Node: ' + str(node_id) + ' Renamed: ' + name

                if args[1] == "state":
                    state = args[2]
                    hubObj.send_state_request(node_id, state)
                    return 'Node: ' + str(node_id) + ' State Changed: ' + state

                if args[1] == "attributes":
                    attrib_name = args[2]
                    return hubObj.get_node_attribute_history(node_id, attrib_name, 1485645112, 1488644112)

                if args[1] == "type":
                    hubObj.send_type_request(node_id)
                    return 'Type Request Sent'

                if args[1] == "detail":
                    return hubObj.get_node(node_id)

            return 'Unknown Argument'

        def do_halt(self, *args):
            # Close up shop
            hubObj.halt()
            serialObj.close()
            return Commander.Exit

        def do_echo(self, *args):
            return ' '.join(args)

        def do_raise(self, *args):
            raise Exception('Some Error')

    c = Commander('PyAlertMe', cmd_cb=TestCmd())


    from pyalertme import *
    import serial
    import logging
    import pprint

    pp = pprint.PrettyPrinter(indent=4)
    logger = logging.getLogger('pyalertme')
    logger.setLevel(logging.DEBUG)

    # Specify log message format
    formatter = logging.Formatter('%(asctime)s %(levelname)-3s %(module)-5s %(message)s')

    # Create console handler and set level to info
    sh = logging.StreamHandler()
    sh.setLevel(logging.DEBUG)
    sh.setFormatter(formatter)
    logger.addHandler(sh)

    # Create debug file handler and set level to debug
    fh = logging.FileHandler("debug.log")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(formatter)
    logger.addHandler(fh)

    # Serial Configuration
    XBEE_PORT = '/dev/tty.usbserial-A1014P7W'  # MacBook Serial Port
    XBEE_BAUD = 9600
    serialObj = serial.Serial(XBEE_PORT, XBEE_BAUD)

    # Start hub
    hubObj = Hub(serialObj)

    # Start main loop
    c.loop()
