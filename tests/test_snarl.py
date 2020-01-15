import io
import pytest
import random
import string

from unittest import mock

import snarl.main


@pytest.fixture(scope='function')
def snarlobj():
    return snarl.main.Snarl()


@pytest.fixture(scope='function')
def randomstring():
    letters = string.ascii_lowercase
    return ''.join(random.choice(letters) for i in range(10))


def test_include_recursive(snarlobj):
    def doc():
        data = '\n'.join(('This is a test',
                          '',
                          '<!-- include recursive.snarl.md -->'
                          ))
        return io.StringIO(data)

    with mock.patch('snarl.main.open', create=True) as mock_open:
        mock_open.side_effect = lambda x, y: doc()
        with pytest.raises(snarl.main.RecursiveIncludeError):
            snarlobj.parse(doc())


def test_include_simple(snarlobj, randomstring):
    parent = '<!-- include simple.snarl.md -->\n'
    child = io.StringIO(randomstring)

    with mock.patch('snarl.main.open', create=True) as mock_open:
        mock_open.side_effect = lambda x, y: child
        snarlobj.parse(parent)
        assert randomstring in '\n'.join(snarlobj.output)


def test_file(snarlobj, randomstring):
    doc = '\n'.join(('```=block0',
                     f'{randomstring}',
                     '```',
                     '```=output.txt --file',
                     '<<block0>>',
                     '```'))

    snarlobj.parse(doc)
    assert 'output.txt' in snarlobj.files
    assert randomstring in ''.join(snarlobj.generate('output.txt'))


def test_lang_block(snarlobj):
    doc = '\n'.join(('```python:block0',
                     'print("This is a test")',
                     '```'))

    snarlobj.parse(doc)
    assert '```python' in '\n'.join(snarlobj.output)


def test_hide_block(snarlobj):
    doc = '\n'.join(('```=block0 --hide',
                     'This should not appear in weave output',
                     '```'))

    snarlobj.parse(doc)
    assert 'This should not appear in weave output' not in '\n'.join(snarlobj.output)


def test_append_block(snarlobj):
    doc = '\n'.join(('```=block0',
                     'this is line1',
                     '```',
                     '```+=block0',
                     'this is line2',
                     '```'))
    snarlobj.parse(doc)
    assert 'this is line2' in '\n'.join(snarlobj.generate('block0'))
