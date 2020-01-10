import click
import enum
import logging
import re
import sys
import tempfile

from pathlib import Path

LOG = logging.getLogger(__name__)


class STATE(enum.Enum):
    INIT = 0
    READ_CODEBLOCK = 1
    READ_FILE = 2


re_start_codeblock = re.compile(r'^```(?P<lang>\w+)?:(?P<label>\w+)'
                                r'( ?(?P<hide>hide))?$')
re_end_codeblock = re.compile(r'^```$')
re_start_file = re.compile(r'^:f(ile)? (?P<label>\S+)$')
re_include_block = re.compile(r'^\|(?P<label>\w+)\|$')
re_end_file = re.compile(r'^:$')
re_start_include = re.compile(r'^:i(nclude)? (?P<path>\S+)$')


class Snarl(object):
    def __init__(self):
        self._files = {}
        self._blocks = {}

        self.outfd = self.new_file('__output__')['fd']

    def write_codeblock(self, block):
        block['fd'].seek(0)
        lang = block['config'].get('lang')
        self.outfd.write('```{}\n'.format(
            lang if lang is not None else ''
        ))
        self.outfd.write(block['fd'].read())
        self.outfd.write('```\n')

    def start_codeblock(self, match):
        blockname = match.group('label')
        LOG.debug('reading codeblock %s', blockname)
        blockconf = dict(
            lang=match.group('lang'),
            hide=match.group('hide')
        )
        self._block = self.new_block(blockname, blockconf)

    def start_file(self, match):
        filename = match.group('label')
        self._file = self.new_file(filename)

    # XXX: Might want to set a maximum include depth to avoid
    # crashing due to a recursive :include.
    def include_file(self, match):
        path = match.group('path')
        LOG.info('including file %s', path)
        with open(path, 'r') as fd:
            self.parse(fd)

    def parse(self, infd):
        state = STATE.INIT

        for ln, line in enumerate(infd):
            LOG.debug('%d [%s]: %s', ln, state, line.rstrip())
            if state == STATE.INIT:
                match = re_start_codeblock.match(line)
                if match:
                    state = STATE.READ_CODEBLOCK
                    self.start_codeblock(match)
                    continue

                match = re_start_file.match(line)
                if match:
                    state = STATE.READ_FILE
                    self.start_file(match)
                    continue

                match = re_start_include.match(line)
                if match:
                    self.include_file(match)
                    continue

                self.outfd.write(line)

            if state == STATE.READ_CODEBLOCK:
                match = re_end_codeblock.match(line)
                if match:
                    state = STATE.INIT

                    if not self._block['config'].get('hide'):
                        self.write_codeblock(self._block)

                    continue

                self._block['fd'].write(line)

            if state == STATE.READ_FILE:
                match = re_end_file.match(line)
                if match:
                    state = STATE.INIT
                    continue

                self._file['fd'].write(line)

        if state != STATE.INIT:
            raise ValueError(state)

    def new_file(self, name):
        LOG.debug('create file %s', name)
        fd = tempfile.SpooledTemporaryFile(mode='w')
        self._files[name] = dict(fd=fd)
        return self._files[name]

    def new_block(self, name, config):
        LOG.debug('create block %s', name)
        fd = tempfile.SpooledTemporaryFile(mode='w')
        self._blocks[name] = dict(fd=fd, config=config)
        return self._blocks[name]

    def generate_file(self, name):
        fd = self._files[name]['fd']
        fd.seek(0)
        for line in fd:
            match = re_include_block.match(line)
            if match:
                blockfd = self._blocks[match.group('label')]['fd']
                blockfd.seek(0)
                yield from blockfd
            else:
                yield line

    @property
    def files(self):
        return [fn for fn in self._files.keys()
                if fn != '__output__']

    @property
    def output(self):
        return self.generate_file('__output__')


@click.group()
@click.option('-v', '--verbose', count=True)
def main(verbose):
    try:
        loglevel = [logging.WARNING, logging.INFO, logging.DEBUG][verbose]
    except IndexError:
        loglevel = logging.DEBUG

    logging.basicConfig(level=loglevel)


@main.command()
@click.option('-o', '--output-path', type=Path, default=Path('.'))
@click.option('--no-files', is_flag=True)
@click.option('-n', '--no-output', is_flag=True)
@click.option('-f', '--file', 'onlyfile', multiple=True)
@click.argument('infile',
                type=click.File(),
                default=sys.stdin)
def tangle(output_path, no_files, no_output, onlyfile, infile):
    with infile:
        snarl = Snarl()
        snarl.parse(infile)

    if not no_files:
        for fn in snarl.files:
            if onlyfile and fn not in onlyfile:
                continue

            fpath = output_path / fn

            LOG.info('writing file %s', fpath)
            with fpath.open('w') as fd:
                for line in snarl.generate_file(fn):
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
        snarl = Snarl()
        snarl.parse(infile)

    with outfile:
        for line in snarl.output:
            outfile.write(line)


if __name__ == '__main__':
    main()
