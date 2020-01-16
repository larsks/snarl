import argparse
import click
import enum
import io
import logging
import re
import shlex
import sys
import tempfile

from pathlib import Path

import snarl.exc

MAX_INCLUDE_DEPTH = 10
LOG = logging.getLogger(__name__)
VDEBUG = 5
logging.addLevelName(VDEBUG, 'VDEBUG')

re_start_codeblock = re.compile(r'^```(?P<lang>\w+)?(?P<append>\+)?=(?P<args>.+)')
re_end_codeblock = re.compile(r'^```$')
re_include_block = re.compile(r'^<<(?P<label>.+)>>$')
re_include_file = re.compile(r'^<!-- i(nclude)? (?P<path>\S+) -->$')


class STATE(enum.Enum):
    INIT = 0
    READ_CODEBLOCK = 1


class Context(object):
    def __init__(self, ln=0, line=None):
        self.ln = ln
        self.line = line


class BlockArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        raise snarl.exc.BlockArgumentError(message)


class Snarl(object):
    def __init__(self):
        self._blocks = {}

        self.outfd = tempfile.SpooledTemporaryFile(mode='w')
        self.parser = self.create_argument_parser()
        self.ctx = Context()

    def create_argument_parser(self):
        p = BlockArgumentParser()
        p.add_argument('--hide', '-H', action='store_true')
        p.add_argument('--file', '-f', action='store_true')
        p.add_argument('--tag', '-t', action='append', default=[])
        p.add_argument('--replace', '-r', nargs=2, action='append', default=[])
        p.add_argument('--lang')
        p.add_argument('label')
        return p

    def start_codeblock(self, match):
        args = shlex.split(match.group('args'))
        if match.group('lang'):
            args.extend(['--lang', match.group('lang')])
        parsed_args = self.parser.parse_args(args)

        if match.group('append'):
            LOG.debug('appending to codeblock %s', parsed_args.label)
            self._block = self._blocks[parsed_args.label]
        else:
            LOG.debug('reading codeblock %s', parsed_args.label)
            self._block = self.new_block(parsed_args.label, parsed_args)

    def write_codeblock(self, block):
        block['fd'].seek(0)
        lang = block['config'].lang
        self.outfd.write('```{}\n'.format(
            lang if lang is not None else ''
        ))
        self.outfd.write(block['fd'].read())
        self.outfd.write('```\n')

    def include_file(self, match, depth):
        path = match.group('path')
        LOG.info('including file %s', path)
        with open(path, 'r') as fd:
            self.parse(fd, depth+1)

    def process_line(self, line, depth):
        match = re_start_codeblock.match(line)
        if match:
            self.start_codeblock(match)
            return (STATE.READ_CODEBLOCK, None)

        match = re_include_file.match(line)
        if match:
            self.include_file(match, depth)
            return (STATE.INIT, None)

        return (STATE.INIT, line)

    def fromstring(self, s):
        return self.parse(io.StringIO(s))

    def parse(self, infd, depth=0):
        state = STATE.INIT
        oldstate = STATE.INIT

        if depth >= MAX_INCLUDE_DEPTH:
            raise snarl.exc.RecursiveIncludeError(depth)

        for ln, line in enumerate(infd):
            self.ctx.ln = ln + 1
            self.ctx.line = line

            LOG.log(VDEBUG, '%s:%d %s | %s',
                    infd.name if hasattr(infd, 'name') else '<none>',
                    ln,
                    state,
                    line.rstrip())

            if oldstate != state:
                LOG.debug('%s -> %s', oldstate, state)
                oldstate = state

            if state == STATE.INIT:
                state, content = self.process_line(line, depth)
                if content is not None:
                    self.outfd.write(content)

                continue

            if state == STATE.READ_CODEBLOCK:
                match = re_end_codeblock.match(line)
                if match:
                    state = STATE.INIT

                    if not self._block['config'].hide:
                        self.write_codeblock(self._block)

                    continue

                self._block['fd'].write(line)

        if state != STATE.INIT:
            raise ValueError(state)

    def new_block(self, name, config):
        LOG.debug('create block %s', name)
        fd = tempfile.SpooledTemporaryFile(mode='w')
        self._blocks[name] = dict(fd=fd, config=config)
        return self._blocks[name]

    def generate(self, label):
        def _generate_block(fd, replaces):
            fd.seek(0)

            for line in fd:
                match = re_include_block.match(line)
                if match:
                    yield from self.generate(match.group('label'))
                else:
                    for pat, sub in replaces:
                        LOG.debug('replacing %s with %s in %s', pat, sub, line.strip())
                        line = re.sub(pat, sub, line)
                    yield line

        block = self._blocks[label]
        return _generate_block(block['fd'], block['config'].replace)

    def blocks(self, tags=None):
        return [k for k in self._blocks.keys()
                if not tags
                or any(t in self._blocks[k]['config'].tag for t in tags)]

    def files(self, tags=None):
        return [k for k in self._blocks.keys()
                if self._blocks[k]['config'].file and (
                    not tags
                    or any(t in self._blocks[k]['config'].tag for t in tags)
                )]

    @property
    def output(self):
        self.outfd.seek(0)
        return self.outfd


def parse(infile):
    try:
        snarl = Snarl()
        snarl.parse(infile)
    except snarl.exc.SnarlError as err:
        raise click.ClickException(f'Parsing failed at line {snarl.ctx.ln}: {err}')
    else:
        return snarl


@click.group()
@click.option('-v', '--verbose', count=True)
def main(verbose):
    try:
        loglevel = [logging.WARNING, logging.INFO,
                    logging.DEBUG, VDEBUG][verbose]
    except IndexError:
        loglevel = logging.DEBUG

    logging.basicConfig(level=loglevel)


@main.command()
@click.option('-o', '--output-path', type=Path, default=Path('.'))
@click.option('-w', '--overwrite', is_flag=True,
              envvar='SNARL_OVERWRITE')
@click.option('--stdout', '-s', is_flag=True)
@click.option('--all', '-a', 'all_blocks', is_flag=True)
@click.option('--tag', '-t', multiple=True)
@click.argument('infile',
                type=click.File(),
                default=sys.stdin)
@click.argument('block', nargs=-1)
def tangle(stdout, output_path, overwrite, all_blocks, tag, infile, block):
    with infile:
        snarl = parse(infile)

    if block:
        to_generate = block
    elif all_blocks:
        to_generate = snarl.blocks(tag)
    else:
        to_generate = snarl.files(tag)

    for fn in to_generate:
        try:
            src = snarl.generate(fn)
        except KeyError:
            raise click.ClickException(f'No such block named "{fn}"')

        if stdout:
            for line in src:
                sys.stdout.write(line)
        else:
            fpath = output_path / fn

            if fpath.is_file() and not overwrite:
                LOG.error('refusing to overwrite existing file %s', fpath)
                continue

            with fpath.open('w') as fd:
                LOG.info('writing file %s', fpath)
                for line in src:
                    fd.write(line)


@main.command()
@click.option('-o', '--output', 'outfile',
              type=click.File('w'),
              default=sys.stdout)
@click.argument('infile',
                type=click.File(),
                default=sys.stdin)
def weave(outfile, infile):
    with infile:
        snarl = parse(infile)

    with outfile:
        for line in snarl.output:
            outfile.write(line)


@main.command()
@click.option('--all', '-a', 'show_all_blocks', is_flag=True)
@click.option('--tag', '-t', multiple=True)
@click.argument('infile',
                type=click.File(),
                default=sys.stdin)
def files(show_all_blocks, tag, infile):
    with infile:
        snarl = parse(infile)

    if show_all_blocks:
        print('\n'.join(snarl.blocks(tag)))
    else:
        print('\n'.join(snarl.files(tag)))


if __name__ == '__main__':
    main()
