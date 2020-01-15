import click
import enum
import logging
import argparse
import re
import shlex
import sys
import tempfile

from pathlib import Path

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


class SnarlError(Exception):
    pass


class RecursiveIncludeError(SnarlError):
    pass


class Context(object):
    def __init__(self, state=STATE.INIT, depth=0):
        self.state = state
        self.depth = 0


class Snarl(object):
    def __init__(self):
        self._blocks = {}

        self.outfd = tempfile.SpooledTemporaryFile(mode='w')
        self.parser = self.create_argument_parser()

    def create_argument_parser(self):
        p = argparse.ArgumentParser()
        p.add_argument('--hide', '-H', action='store_true')
        p.add_argument('--file', '-f', action='store_true')
        p.add_argument('--tag', '-t', action='append', default=[])
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
        if line.startswith(':'):
            if line.startswith('::'):
                line = line[1:]
                return (STATE.INIT, line)

        match = re_start_codeblock.match(line)
        if match:
            self.start_codeblock(match)
            return (STATE.READ_CODEBLOCK, None)

        match = re_include_file.match(line)
        if match:
            self.include_file(match, depth)
            return (STATE.INIT, None)

        return (STATE.INIT, line)

    def parse(self, infd, depth=0):
        state = STATE.INIT
        oldstate = STATE.INIT

        if depth >= MAX_INCLUDE_DEPTH:
            raise RecursiveIncludeError(depth)

        for ln, line in enumerate(infd):
            LOG.log(VDEBUG, '%s:%d %s | %s', infd.name, ln,
                    state, line.rstrip())

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
        def _generate_block(fd):
            fd.seek(0)

            for line in fd:
                match = re_include_block.match(line)
                if match:
                    blockfd = self._blocks[match.group('label')]['fd']
                    blockfd.seek(0)
                    yield from blockfd
                else:
                    yield line

        fd = self._blocks[label]['fd']
        return _generate_block(fd)

    @property
    def blocks(self):
        return self._blocks.keys()

    @property
    def files(self):
        return [k for k, v in self._blocks.items()
                if v['config'].file]

    @property
    def output(self):
        self.outfd.seek(0)
        return self.outfd


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
@click.argument('infile',
                type=click.File(),
                default=sys.stdin)
@click.argument('block', nargs=-1)
def tangle(output_path, overwrite, infile, block):
    with infile:
        snarl = Snarl()
        snarl.parse(infile)

    to_generate = block if block else snarl.files
    for fn in to_generate:
        fpath = output_path / fn

        if fpath.is_file() and not overwrite:
            LOG.error('refusing to overwrite existing file %s', fpath)
            continue

        try:
            src = snarl.generate(fn)
            with fpath.open('w') as fd:
                LOG.info('writing file %s', fpath)
                for line in src:
                    fd.write(line)
        except KeyError:
            raise click.ClickException(f'No such block named "{fn}"')


@main.command()
@click.option('-o', '--output', 'outfile',
              type=click.File('w'),
              default=sys.stdout)
@click.argument('infile',
                type=click.File(),
                default=sys.stdin)
def weave(outfile, infile):
    with infile:
        snarl = Snarl()
        snarl.parse(infile)

    with outfile:
        for line in snarl.output:
            outfile.write(line)


@main.command()
@click.option('--all', '-a', 'show_all_blocks', is_flag=True)
@click.argument('infile',
                type=click.File(),
                default=sys.stdin)
def files(show_all_blocks, infile):
    with infile:
        snarl = Snarl()
        snarl.parse(infile)

    if show_all_blocks:
        print('\n'.join(snarl.blocks))
    else:
        print('\n'.join(snarl.files))


if __name__ == '__main__':
    main()
