#!/usr/bin/env python3

import re
from argparse import ArgumentParser
from subprocess import run
from os import makedirs, walk
from os.path import dirname, basename, realpath, expanduser, isdir
from os.path import join as join_path, exists, getmtime, splitext
from ast import literal_eval

from pegparse import ASTWalker, create_parser_from_file

CACHE_DIR = '~/.cache/blib'
LIBRARY_DIR = '~/papers'

CACHE_DIR = realpath(expanduser(CACHE_DIR))
LIBRARY_DIR = realpath(expanduser(LIBRARY_DIR))

BIBTEX_PATH = '~/scholarship/journal/library.bib'
TAGS_PATH = '~/scholarship/journal/papers'
REMOTE_HOST = 'justinnhli.com'
REMOTE_PATH = '/home/justinnhli/justinnhli.com/papers'

BIBTEX_PATH = realpath(expanduser(BIBTEX_PATH))
TAGS_PATH = realpath(expanduser(TAGS_PATH))
REMOTE_PATH = realpath(expanduser(REMOTE_PATH))

BIBTEX_CACHE_PATH = join_path(CACHE_DIR, 'bibtex')


WEIRD_NAMES = {
    'Computing Research Association': 'CRA',
    'Liberal Arts Computer Science Consortium': 'LACS',
    'The College Board': 'CB',
    'The Join Task Force on Computing Curricula': 'JTFCC',
    'others': '',
    '{Google Inc.}': 'Google',
    '{Gallup Inc.}': 'Gallup',
    '{National Academies of Sciences, Engineering, and Medicine}': 'NASEM',
    '{UMBEL Project}': 'UMBEL',
    '{the ABC Research Group}': 'ABC',
}

class BibTexWalker(ASTWalker):

    # pylint: disable = invalid-name, unused-argument, no-self-use

    def __init__(self):
        """Initialize a ReactionWalker."""
        super().__init__(
            create_parser_from_file(join_path(
                dirname(realpath(__file__)),
                'bibtex.ebnf',
            )),
            'BibtexFile',
        )

    def _parse_BibtexFile(self, ast, results):
        return dict(results)

    def _parse_BibtexEntry(self, ast, results):
        bibtex_type = results[0]
        bibtex_id = results[1]
        attrs = results[2:]
        return tuple([
            bibtex_id,
            dict([
                ['type', bibtex_type],
                *attrs,
            ]),
        ])

    def _parse_EntryID(self, ast, results):
        return ast.match

    def _parse_BibtexType(self, ast, results):
        return ast.match

    def _parse_BibtexPropertyValue(self, ast, results):
        return results

    def _parse_BibtexProperty(self, ast, results):
        return ast.match

    def _parse_BibtexValue(self, ast, results):
        return ast.match


PARSER = BibTexWalker()


def main():
    arg_parser = ArgumentParser()
    actions = [
        # local management functions
        'read', 'tag', 'lint',
        # database functions
        'organizations', 'publishers', 'journals', 'conferences', 'people', 'tags',
        # remote management functions
        'index', 'sync', 'diff', 'push', 'pull', 'url', 'remove',
    ]
    arg_parser.add_argument(dest='action', action='store', choices=actions)
    arg_parser.add_argument(dest='terms', action='store', nargs='*')
    args = arg_parser.parse_args()
    if args.action in ['read', 'tag', 'url', 'remove'] and not args.terms:
        arg_parser.error(f'Action "{args.action}" requires additional arguments')
    assert f'_do_{args.action}' in globals(), f'Cannot find function _do_{args.action}'
    globals()[f'_do_{args.action}'](*args.terms)


# utilities


def _well_named(name):
    """Check if a name follows the convention.

    The convention is AuthorYearBlurb, with no punctuation.

    Arguments:
        name (str): The name of the file.

    Returns:
        bool: True if the name follows the convention.
    """
    return re.match('[a-z]+[0-9]{4}[0-9a-z]+(.pdf)?$', basename(name), re.IGNORECASE)


def _rel_path(filepath):
    if not _well_named(filepath):
        print(f'WARNING: file {filepath} does not match AuthorYearBlurb convention')
    if not filepath.endswith('.pdf'):
        filepath += '.pdf'
    filepath = basename(filepath)
    return join_path(filepath[0].lower(), filepath)


def _get_url(filepath):
    if not filepath.endswith('.pdf'):
        filepath += '.pdf'
    return 'https://' + join_path(REMOTE_HOST, 'papers', _rel_path(filepath))


def _store(filepath):
    old_path = realpath(expanduser(filepath))
    new_path = join_path(LIBRARY_DIR, _rel_path(old_path))
    if old_path != new_path:
        _run_shell_command('mv', old_path, new_path)


def _get_library():
    papers = {}
    for path, _, files in walk(LIBRARY_DIR):
        papers.update([basename(f)[:-4], join_path(path, f)] for f in files if f.endswith('.pdf'))
    return papers


def _run_shell_command(command, *args, capture_output=False, verbose=True):
    if verbose:
        print(command + ' ' + ' '.join(
            (arg if arg.startswith('-') else f'"{arg}"')
            for arg in args
        ))
    return run([command, *args], capture_output=capture_output)


def _yield_all_attributes(*attributes, filter_fn=None):
    for entry in _read_bibtex().values():
        if filter_fn and not filter_fn(entry):
            continue
        for role in attributes:
            if role in entry:
                yield entry[role]


def _read_bibtex(use_cache=True):
    if use_cache and exists(BIBTEX_CACHE_PATH) and getmtime(BIBTEX_CACHE_PATH) > getmtime(BIBTEX_PATH):
        with open(BIBTEX_CACHE_PATH) as fd:
            return literal_eval(fd.read())
    if not isdir(dirname(BIBTEX_CACHE_PATH)):
        makedirs(dirname(BIBTEX_CACHE_PATH))
    data = PARSER.parse_file(BIBTEX_PATH)
    with open(BIBTEX_CACHE_PATH, 'w') as fd:
        fd.write(repr(data))
    return data


def _read_tags():
    result = {}
    with open(TAGS_PATH) as fd:
        for line in fd.readlines():
            line = line.strip()
            if not line:
                continue
            entry_id, *tags = line.split(' ')
            result[entry_id] = set(tags)
    return result


# main actions


def _do_read(*filepaths):
    for filepath in filepaths:
        _store(filepath)


def _do_tag(filepath, *tags):
    _store(filepath)
    stem = splitext(basename(filepath))[0]
    with open(TAGS_PATH, 'a') as fd:
        fd.write(' '.join([stem, *tags]) + '\n')


def _do_lint():

    entries = _read_bibtex()
    # check for non "last, first" authors and editors
    for entry_id, entry in entries.items():
        for attribute in ['author', 'editor']:
            if attribute not in entry:
                continue
            people = entry[attribute].split(' and ')
            if any((',' not in person) for person in people if person not in WEIRD_NAMES):
                print(f'unconforming {attribute}s in {entry_id}:')
                print(f'    current: {entry[attribute]}')
                pattern = '(?P<first>[A-Z][^ ]*( [A-Z][^ ]*)*) (?P<last>.*)'
                suggestion = ' and '.join([
                    person if person in WEIRD_NAMES
                    else re.sub(
                        pattern,
                        (lambda match: match.group('last') + ', ' + match.group('first')),
                        person)
                    for person in people
                ])
                print(f'    suggested: {suggestion}')
    # check for incorrectly-formed IDs
    for current_id, entry in entries.items():
        first_author = entry['author'].split(' and ')[0]
        first_author = WEIRD_NAMES.get(first_author, first_author.split(',')[0])
        entry_id = first_author + entry['year'] + entry['title']
        entry_id = re.sub(r'\\.{(.)}', r'\1', entry_id)
        entry_id = re.sub('[^0-9A-Za-z]', '', entry_id)
        if not entry_id.lower().startswith(current_id.lower()):
            print(f'suspicious ID: {current_id.lower()} vs {entry_id.lower()}')
            print(f'    {current_id.lower()}')
            print(f'    {entry_id.lower()}')
    # make sure all files in the library have an entry
    library = _get_library()
    for key in set(library.keys()) - set(entries.keys()):
        print('missing entry for file {}'.format(library[key]))
    # make sure all unusual words are quoted
    for entry_id, entry in entries.items():
        for word in entry['title'].split():
            if '{' in word:
                continue
            word = re.sub('[-/][A-Z]', '', word)
            # TODO this check fails for (eg.) {Response to {Adams and McDonnell}}
            if len(re.findall('[A-Za-z][A-Z]', word)) > 1:
                print('unquoted title for {}: {}'.format(entry_id, entry['title']))
                break
    '''
    # make sure all journals have the same publisher
    journals = {}
    for entry_id, entry in entries.items():
        if entry.bibtex_type != 'article':
            continue
        journal = entry.attributes['journal']
        if journal in journals:
            if 'publisher' not in entry.attributes:
                print('publisher for journal "{}" is "{}"'.format(journal, journals[journal]))
            elif journals[journal] != entry.attributes['publisher']:
                print('publisher mismatch for journal: {}'.format(journal))
        elif 'publisher' not in entry.attributes:
            print('missing journal publisher: {}'.format(entry_id))
    '''
    # FIXME make sure all books(collections) have the same address, editor, month, publisher, and year
    # FIXME potentially check required fields


def _do_organizations():
    for organization in _yield_all_attributes('institution', 'school'):
        print(organization)


def _do_publishers():
    for publisher in _yield_all_attributes('publisher'):
        print(publisher)


def _do_journals():
    for journal in _yield_all_attributes('journal'):
        print(journal)


def _do_conferences():
    generator = _yield_all_attributes(
        'booktitle',
        filter_fn=(lambda entry: entry['type'] == 'inproceedings'),
    )
    for conference in generator:
        print(conference)


def _do_people():
    for people in _yield_all_attributes('author', 'editor'):
        for person in people.split(' and '):
            print(person)


def _do_tags():
    tags = set.union(*(_read_tags().values()))
    for tag in sorted(tags, key=str.lower):
        print(tag)


def _do_index():
    index_path = join_path(LIBRARY_DIR, 'index.html')
    with open(index_path, 'w') as fd:
        fd.write('<pre>\n')
        for entry_id, entry in sorted(_read_bibtex().items()):
            entry_type = entry['type']
            url = _get_url(entry_id)
            fd.write(f'@{entry_type} {{<a href="{url}">{entry_id}</a>,\n')
            for attr, value in sorted(entry.items()):
                if attr == 'type':
                    continue
                fd.write(f'    {attr} = {{{value}}},\n')
            fd.write('}\n')
            fd.write('\n')
        fd.write('</pre>\n')


def _do_sync():
    _do_pull()
    _do_index()
    _do_push()


def _do_diff():
    """Original shell script:

    local_list="$(cd "$LOCAL_PATH" && find . -name '*.pdf')"
    remote_list="$()"
    result="$(diff <(echo "$local_list" | sort) <(echo "$remote_list" | sort))"
    if [ "$result" != "" ]; then
        echo 'diff local remote'
        echo "$result"
    fi;;
    """
    local_files = _run_shell_command(
        'find',
        LIBRARY_DIR,
        '-name', '*.pdf',
        capture_output=True,
        verbose=False,
    ).stdout.decode('utf-8').splitlines()
    remote_files = _run_shell_command(
        'ssh',
        REMOTE_HOST,
        f"find {REMOTE_PATH} -name '*.pdf'",
        capture_output=True,
        verbose=False,
    ).stdout.decode('utf-8').splitlines()
    local_files = set(basename(path) for path in local_files)
    remote_files = set(basename(path) for path in remote_files)
    lines = {}
    for diff in local_files - remote_files:
        lines[diff] = '<'
    for diff in remote_files - local_files:
        lines[diff] = '>'
    for diff, symbol in sorted(lines.items()):
        print(f'{symbol} {diff}')


def _do_push():
    _run_shell_command(
        'rsync',
        '--archive',
        '--progress',
        '--rsh=ssh',
        '--exclude', '.*',
        f'{LIBRARY_DIR}/',
        f'{REMOTE_HOST}:{REMOTE_PATH}',
    )


def _do_pull():
    _run_shell_command(
        'rsync',
        '--archive',
        '--progress',
        '--rsh=ssh',
        '--exclude', '.*',
        f'{REMOTE_HOST}:{REMOTE_PATH}/',
        LIBRARY_DIR,
    )


def _do_url(*filepaths):
    for filepath in filepaths:
        print(_get_url(filepath))


def _do_remove(*filepaths):
    for filepath in filepaths:
        remote_path = join_path(REMOTE_PATH, _rel_path(filepath))
        _run_shell_command('ssh', REMOTE_HOST, f"rm -vf '{remote_path}'")
        _run_shell_command('rm', '-vf', join_path(LIBRARY_DIR, _rel_path(filepath)))


if __name__ == '__main__':
    main()
