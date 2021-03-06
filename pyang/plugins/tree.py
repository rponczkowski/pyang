"""Tree output plugin

Idea copied from libsmi.
"""

import optparse
import sys
import re
import string

from pyang import plugin
from pyang import statements

def pyang_plugin_init():
    plugin.register_plugin(TreePlugin())

class TreePlugin(plugin.PyangPlugin):
    def add_output_format(self, fmts):
        self.multiple_modules = True
        fmts['tree'] = self

    def add_opts(self, optparser):
        optlist = [
            optparse.make_option("--tree-help",
                                 dest="tree_help",
                                 action="store_true",
                                 help="Print help on tree symbols and exit"),
            optparse.make_option("--tree-depth",
                                 type="int",
                                 dest="tree_depth",
                                 help="Number of levels to print"),
            optparse.make_option("--tree-path",
                                 dest="tree_path",
                                 help="Subtree to print"),
            ]
        g = optparser.add_option_group("Tree output specific options")
        g.add_options(optlist)

    def setup_ctx(self, ctx):
        if ctx.opts.tree_help:
            print_help()
            sys.exit(0)

    def setup_fmt(self, ctx):
        ctx.implicit_errors = False

    def emit(self, ctx, modules, fd):
        if ctx.opts.tree_path is not None:
            path = string.split(ctx.opts.tree_path, '/')
            if path[0] == '':
                path = path[1:]
        else:
            path = None
        emit_tree(ctx, modules, fd, ctx.opts.tree_depth, path)

def print_help():
    print("""
Each node is printed as:

<status> <flags> <name> <opts> <type> <if-features>

  <status> is one of:
    +  for current
    x  for deprecated
    o  for obsolete

  <flags> is one of:
    rw  for configuration data
    ro  for non-configuration data
    -x  for rpcs
    -n  for notifications

  <name> is the name of the node
    (<name>) means that the node is a choice node
   :(<name>) means that the node is a case node

   If the node is augmented into the tree from another module, its
   name is printed as <prefix>:<name>.

  <opts> is one of:
    ?  for an optional leaf or choice
    !  for a presence container
    *  for a leaf-list or list
    [<keys>] for a list's keys

  <type> is the name of the type for leafs and leaf-lists

    If the type is a leafref, the type is printed as "-> TARGET", where
    TARGET is either the leafref path, with prefixed removed if possible.

  <if-features> is the list of features this node depends on, printed
    within curly brackets and a question mark "{...}?"
""")

def emit_tree(ctx, modules, fd, depth, path):
    for module in modules:
        printed_header = False

        def print_header():
            bstr = ""
            b = module.search_one('belongs-to')
            if b is not None:
                bstr = " (belongs-to %s)" % b.arg
            fd.write("%s: %s%s\n" % (module.keyword, module.arg, bstr))
            printed_header = True

        chs = [ch for ch in module.i_children
               if ch.keyword in statements.data_definition_keywords]
        if path is not None and len(path) > 0:
            chs = [ch for ch in chs if ch.arg == path[0]]
            path = path[1:]

        if len(chs) > 0:
            if not printed_header:
                print_header()
                printed_header = True
            print_children(chs, module, fd, ' ', path, 'data', depth)

        mods = [module]
        for i in module.search('include'):
            subm = ctx.get_module(i.arg)
            if subm is not None:
                mods.append(subm)
        for m in mods:
            for augment in m.search('augment'):
                if (hasattr(augment.i_target_node, 'i_module') and
                    augment.i_target_node.i_module not in modules + mods):
                    # this augment has not been printed; print it
                    if not printed_header:
                        print_header()
                        printed_header = True
                    fd.write("augment %s:\n" % augment.arg)
                    print_children(augment.i_children, m, fd,
                                   ' ', path, 'augment', depth)

        rpcs = [ch for ch in module.i_children
                if ch.keyword == 'rpc']
        if path is not None:
            if len(path) > 0:
                rpcs = [rpc for rpc in rpcs if rpc.arg == path[0]]
                path = path[1:]
            else:
                rpcs = []
        if len(rpcs) > 0:
            if not printed_header:
                print_header()
                printed_header = True
            fd.write("rpcs:\n")
            print_children(rpcs, module, fd, ' ', path, 'rpc', depth)

        notifs = [ch for ch in module.i_children
                  if ch.keyword == 'notification']
        if path is not None:
            if len(path) > 0:
                notifs = [n for n in notifs if n.arg == path[0]]
                path = path[1:]
            else:
                notifs = []
        if len(notifs) > 0:
            if not printed_header:
                print_header()
                printed_header = True
            fd.write("notifications:\n")
            print_children(notifs, module, fd, ' ', path, 'notification', depth)

def print_children(i_children, module, fd, prefix, path, mode, depth, width=0):
    if depth == 0:
        if i_children: fd.write(prefix + '     ...\n')
        return
    def get_width(w, chs):
        for ch in chs:
            if ch.keyword in ['choice', 'case']:
                w = get_width(w, ch.i_children)
            else:
                if ch.i_module.i_modulename == module.i_modulename:
                    nlen = len(ch.arg)
                else:
                    nlen = len(ch.i_module.i_prefix) + 1 + len(ch.arg)
                if nlen > w:
                    w = nlen
        return w

    if width == 0:
        width = get_width(0, i_children)

    for ch in i_children:
        if ((ch.keyword == 'input' or ch.keyword == 'output') and
            len(ch.i_children) == 0):
            pass
        else:
            if (ch == i_children[-1] or
                (i_children[-1].keyword == 'output' and
                 len(i_children[-1].i_children) == 0)):
                # the last test is to detect if we print input, and the
                # next node is an empty output node; then don't add the |
                newprefix = prefix + '   '
            else:
                newprefix = prefix + '  |'
            if ch.keyword == 'input':
                mode = 'input'
            elif ch.keyword == 'output':
                mode = 'output'
            print_node(ch, module, fd, newprefix, path, mode, depth, width)

def print_node(s, module, fd, prefix, path, mode, depth, width):
    fd.write("%s%s--" % (prefix[0:-1], get_status_str(s)))

    if s.i_module.i_modulename == module.i_modulename:
        name = s.arg
    else:
        name = s.i_module.i_prefix + ':' + s.arg
    flags = get_flags_str(s, mode)
    if s.keyword == 'list':
        name += '*'
        fd.write(flags + " " + name)
    elif s.keyword == 'container':
        p = s.search_one('presence')
        if p is not None:
            name += '!'
        fd.write(flags + " " + name)
    elif s.keyword  == 'choice':
        m = s.search_one('mandatory')
        if m is None or m.arg == 'false':
            fd.write(flags + ' (' + s.arg + ')?')
        else:
            fd.write(flags + ' (' + s.arg + ')')
    elif s.keyword == 'case':
        fd.write(':(' + s.arg + ')')
    else:
        if s.keyword == 'leaf-list':
            name += '*'
        elif s.keyword == 'leaf' and not hasattr(s, 'i_is_key'):
            m = s.search_one('mandatory')
            if m is None or m.arg == 'false':
                name += '?'
        t = get_typename(s)
        if t == '':
            fd.write("%s %s" % (flags, name))
        else:
            fd.write("%s %-*s   %s" % (flags, width+1, name, t))

    if s.keyword == 'list' and s.search_one('key') is not None:
        fd.write(" [%s]" % re.sub('\s+', ' ', s.search_one('key').arg))

    features = s.search('if-feature')
    if len(features) > 0:
        fd.write(" {%s}?" % ",".join([f.arg for f in features]))

    fd.write('\n')
    if hasattr(s, 'i_children'):
        if depth is not None:
            depth = depth - 1
        chs = s.i_children
        if path is not None and len(path) > 0:
            chs = [ch for ch in chs
                   if ch.arg == path[0]]
            path = path[1:]
        if s.keyword in ['choice', 'case']:
            print_children(chs, module, fd, prefix, path, mode, depth, width)
        else:
            print_children(chs, module, fd, prefix, path, mode, depth)

def get_status_str(s):
    status = s.search_one('status')
    if status is None or status.arg == 'current':
        return '+'
    elif status.arg == 'deprecated':
        return 'x'
    elif status.arg == 'obsolete':
        return 'o'

def get_flags_str(s, mode):
    if mode == 'input':
        return "-w"
    elif (s.keyword == 'rpc' or s.keyword == ('tailf-common', 'action')):
        return '-x'
    elif s.keyword == 'notification':
        return '-n'
    elif s.i_config == True:
        return 'rw'
    elif s.i_config == False or mode == 'output' or mode == 'notification':
        return 'ro'
    else:
        return '--'

def get_typename(s):
    t = s.search_one('type')
    if t is not None:
        if t.arg == 'leafref':
            p = t.search_one('path')
            if p is not None:
                # Try to make the path as compact as possible.
                # Remove local prefixes, and only use prefix when
                # there is a module change in the path.
                target = []
                curprefix = s.i_module.i_prefix
                for name in p.arg.split('/'):
                    if name.find(":") == -1:
                        prefix = curprefix
                    else:
                        [prefix, name] = name.split(':', 1)
                    if prefix == curprefix:
                        target.append(name)
                    else:
                        target.append(prefix + ':' + name)
                        curprefix = prefix
                return "-> %s" % "/".join(target)
            else:
                return t.arg
        else:
            return t.arg
    else:
        return ''
