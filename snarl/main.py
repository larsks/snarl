import argparse
import click
import enum
import html
import io
import itertools
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

re_start_codeblock = re.compile(r'^```(?P<lang>\w+)?((?P<append>\+)?=(?P<args>.+))?')
re_end_codeblock = re.compile(r'^```$')
re_include_block = re.compile(r'^\s*<<(?P<label>.+)>>$')
re_include_file = re.compile(r'^<!-- i(nclude)? (?P<args>.*) -->$')


class STATE(enum.Enum):
    INIT = 0
    READ_CODEBLOCK = 1


class Context(object):
    def __init__(self, ln=0, line=None, block=None):
        self.ln = ln
        self.line = line
        block = block


class ArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        raise snarl.exc.BlockArgumentError(message)


def html_escaper(fd):
    for line in fd:
        yield html.escape(line)


class Snarl(object):
    def __init__(self, ignore_missing=False):
        self._blocks = {}

        self.outfd = tempfile.SpooledTemporaryFile(mode='w')
        self.block_parser = self.create_block_parser()
        self.include_parser = self.create_include_parser()
        self.ctx = Context()
        self.blocknum = itertools.count()
        self.ignore_missing = ignore_missing

    def create_block_parser(self):
        p = ArgumentParser()
        p.add_argument('--hide', '-H', action='store_true')
        p.add_argument('--file', '-f', action='store_true')
        p.add_argument('--tag', '-t', action='append', default=[])
        p.add_argument('--replace', '-r', nargs=2, action='append', default=[])
        p.add_argument('--escape-html', action='store_true')
        p.add_argument('--verbatim', action='store_true')
        p.add_argument('--lang')
        p.add_argument('label', nargs='?')
        return p

    def create_include_parser(self):
        p = ArgumentParser()
        p.add_argument('--escape-html', '-e', action='store_true')
        p.add_argument('--verbatim', '-v', action='store_true')
        p.add_argument('path')
        return p

    def start_codeblock(self, match):
        args = shlex.split(match.group('args') or '')
        if match.group('lang'):
            args.extend(['--lang', match.group('lang')])
        parsed_args = self.block_parser.parse_args(args)

        if not parsed_args.label:
            parsed_args.label = '__autoblock{}'.format(next(self.blocknum))

        if match.group('append'):
            LOG.debug('appending to codeblock %s', parsed_args.label)
            self.ctx.block = self._blocks[parsed_args.label]
        else:
            LOG.debug('reading codeblock %s', parsed_args.label)
            self.ctx.block = self.new_block(parsed_args)

    def write_codeblock(self, block):
        '''Write a code block into the generated document when weaving'''

        lang = block['config'].lang
        self.outfd.write('```{}\n'.format(
            lang if lang is not None else ''
        ))

        fd = block['fd']
        fd.seek(0)

        if block['config'].escape_html:
            fd = html_escaper(block['fd'])

        for line in fd:
            self.outfd.write(line)
        self.outfd.write('```\n')

    def include_file(self, match, depth):
        args = shlex.split(match.group('args'))
        parsed_args = self.include_parser.parse_args(args)

        LOG.info('including file %s', parsed_args.path)
        try:
            with open(parsed_args.path, 'r') as fd:
                if parsed_args.escape_html:
                    fd = html_escaper(fd)

                if parsed_args.verbatim:
                    self.include_verbatim(fd)
                else:
                    self.parse(fd, depth+1)
        except FileNotFoundError:
            if self.ignore_missing:
                LOG.error(f'ignorning missing include file "{parsed_args.path}"')
            else:
                raise

    def include_verbatim(self, fd):
        for line in fd:
            self.outfd.write(line)

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

                    if not self.ctx.block['config'].hide:
                        self.write_codeblock(self.ctx.block)

                    continue

                self.ctx.block['fd'].write(line)

        if state != STATE.INIT:
            raise snarl.exc.UnexpectedEOFError('Unexpected end-of-file')

    def new_block(self, config):
        label = config.label
        LOG.debug('create block %s', label)
        fd = tempfile.SpooledTemporaryFile(mode='w')
        self._blocks[label] = dict(fd=fd, config=config)
        return self._blocks[label]

    def generate(self, label):
        '''Return an iterator for the lines of a code block.

        This method is used when weaving. It takes care of interpreting
        `<<blockname>>` markers.
        '''

        def _generate_block(block):
            fd = block['fd']
            fd.seek(0)

            for line in fd:
                match = re_include_block.match(line)
                if match and not block['config'].verbatim:
                    LOG.debug('including block %s', match.group('label'))
                    yield from self.generate(match.group('label'))
                else:
                    for pat, sub in block['config'].replace:
                        LOG.debug('replacing %s with %s in %s', pat, sub, line.strip())
                        line = re.sub(pat, sub, line)
                    yield line

        block = self._blocks[label]
        return _generate_block(block)

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


@click.group()
@click.option('-v', '--verbose', count=True)
@click.option('--ignore-missing', '-i', is_flag=True)
@click.pass_context
def main(ctx, verbose, ignore_missing):
    try:
        loglevel = [logging.WARNING, logging.INFO,
                    logging.DEBUG, VDEBUG][verbose]
    except IndexError:
        loglevel = logging.DEBUG

    logging.basicConfig(level=loglevel)

    ctx.obj = Snarl(ignore_missing=ignore_missing)


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
@click.pass_context
def tangle(ctx, stdout, output_path, overwrite, all_blocks,
           tag, infile, block):
    snarlobj = ctx.obj

    with infile:
        try:
            snarlobj.parse(infile)
        except snarl.exc.SnarlError as err:
            raise click.ClickException(f'Parsing failed at line {snarl.ctx.ln}: {err}')

    if block:
        to_generate = block
    elif all_blocks:
        to_generate = snarlobj.blocks(tag)
    else:
        to_generate = snarlobj.files(tag)

    for fn in to_generate:
        try:
            src = snarlobj.generate(fn)
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
@click.pass_context
def weave(ctx, outfile, infile):
    snarlobj = ctx.obj

    with infile:
        try:
            snarlobj.parse(infile)
        except snarl.exc.SnarlError as err:
            raise click.ClickException(f'Parsing failed at line {snarl.ctx.ln}: {err}')

    with outfile:
        for line in snarlobj.output:
            outfile.write(line)


@main.command()
@click.option('--all', '-a', 'show_all_blocks', is_flag=True)
@click.option('--tag', '-t', multiple=True)
@click.argument('infile',
                type=click.File(),
                default=sys.stdin)
@click.pass_context
def files(ctx, show_all_blocks, tag, infile):
    snarlobj = ctx.obj

    with infile:
        try:
            snarlobj.parse(infile)
        except snarl.exc.SnarlError as err:
            raise click.ClickException(f'Parsing failed at line {snarl.ctx.ln}: {err}')

    if show_all_blocks:
        print('\n'.join(snarlobj.blocks(tag)))
    else:
        print('\n'.join(snarlobj.files(tag)))


if __name__ == '__main__':
    main()
