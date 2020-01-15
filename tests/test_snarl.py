import io
import pytest
import random
import string

from unittest import mock

import snarl.main


class NamedBuffer(io.StringIO):
    def __init__(self, value=None, name=None):
        super().__init__(value)
        self.name = name


@pytest.fixture(scope='function')
def snarlobj():
    return snarl.main.Snarl()


@pytest.fixture(scope='function')
def randomstring():
    letters = string.ascii_lowercase
    return ''.join(random.choice(letters) for i in range(10))


def test_include_recursive(snarlobj):
    def doc():
        return NamedBuffer('This is a test\n\n'
                           '<!-- include recursive.snarl.md -->\n',
                           name='recursive.snarl.md')

    with mock.patch('snarl.main.open', create=True) as mock_open:
        mock_open.side_effect = lambda x, y: doc()
        with pytest.raises(snarl.main.RecursiveIncludeError):
            snarlobj.parse(doc())


def test_include_simple(snarlobj, randomstring):
    parent = NamedBuffer('<!-- include simple.snarl.md -->\n')
    child = NamedBuffer(randomstring)

    with mock.patch('snarl.main.open', create=True) as mock_open:
        mock_open.side_effect = lambda x, y: child
        snarlobj.parse(parent)
        assert randomstring in '\n'.join(snarlobj.output)


def test_file(snarlobj, randomstring):
    doc = NamedBuffer('```=block0\n'
                      f'{randomstring}\n'
                      '```\n'
                      '```=output.txt --file\n'
                      '<<block0>>\n'
                      '```')

    snarlobj.parse(doc)
    assert 'output.txt' in snarlobj.files
    assert randomstring in ''.join(snarlobj.generate('output.txt'))


def test_lang_block(snarlobj):
    doc = NamedBuffer('```python:block0\n'
                      'print("This is a test")\n'
                      '```\n')

    snarlobj.parse(doc)
    assert '```python' in '\n'.join(snarlobj.output)


def test_hide_block(snarlobj):
    doc = NamedBuffer('```=block0 --hide\n'
                      'This should not appear in weave output\n'
                      '```\n')

    snarlobj.parse(doc)
    assert 'This should not appear in weave output' not in '\n'.join(snarlobj.output)


def test_append_block(snarlobj):
    doc = NamedBuffer('```=block0\n'
                      'this is line1\n'
                      '```\n\n'
                      '```+=block0\n'
                      'this is line2\n'
                      '```\n')
    snarlobj.parse(doc)
    assert 'this is line2' in '\n'.join(snarlobj.generate('block0'))
