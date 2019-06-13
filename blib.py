#!/usr/bin/env python3

import re
from argparse import ArgumentParser
from ast import literal_eval
from collections import Counter, defaultdict
from distutils.spawn import find_executable
from os import makedirs, walk
from os.path import getmtime
from pathlib import Path
from subprocess import run

from pegparse import ASTWalker, create_parser_from_file

CACHE_DIR = Path('~/.cache/blib').expanduser().resolve()
LIBRARY_DIR = Path('~/papers').expanduser().resolve()

BIBTEX_PATH = Path('~/scholarship/journal/library.bib').expanduser().resolve()
TAGS_PATH = Path('~/scholarship/journal/papers').expanduser().resolve()
REMOTE_HOST = 'justinnhli.com'
REMOTE_PATH = Path('/home/justinnhli/justinnhli.com/papers').resolve()

BIBTEX_CACHE_PATH = CACHE_DIR.joinpath('bibtex')


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

ID_SUFFIXES = [
    '[0-9]+',
    'Thesis',
]

class BibTexWalker(ASTWalker):

    # pylint: disable = invalid-name, unused-argument, no-self-use

    def __init__(self):
        """Initialize a ReactionWalker."""
        super().__init__(
            create_parser_from_file(Path(__file__).parent.joinpath('bibtex.ebnf')),
            'BibtexFile',
        )

    def _parse_BibtexFile(self, ast, results):
        id_counts = Counter(kv[0] for kv in results)
        for entry_id, count in id_counts.most_common():
            if count == 1:
                break
            print(f'duplicate IDs: {entry_id}')
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
    function = f'do_{args.action}'
    assert f'{function}' in globals(), f'Cannot find function {function}'
    globals()[function](*args.terms)


# utilities


def find_md5():
    """Determine the md5 executable and its appropriate options.

    Returns:
        List[str]: The command to run md5.

    Raises:
        FileNotFoundError: If no known md5 executable can be found.
    """
    md5_path = find_executable('md5sum')
    if md5_path:
        return [md5_path]
    md5_path = find_executable('md5')
    if md5_path:
        return [md5_path, '-r']
    raise FileNotFoundError('cannot locate md5sum or md5')


def _well_named(path):
    """Check if a name follows the convention.

    The convention is AuthorYearBlurb, with no punctuation.

    Arguments:
        path (Path): The name of the file.

    Returns:
        bool: True if the name follows the convention.
    """
    return re.fullmatch('[a-z]+[0-9]{4}[0-9a-z]+(.pdf)?', path.name, flags=re.IGNORECASE)


def _get_url(filepath):
    filepath = Path(filepath)
    return 'https://' + str(Path(REMOTE_HOST, 'papers', filepath.name[0].lower(), filepath.stem + '.pdf'))


def _store(old_path):
    old_path = Path(old_path).expanduser().resolve()
    new_path = Path(LIBRARY_DIR, old_path.name[0].lower(), old_path.stem + '.pdf')
    if old_path != new_path:
        _run_shell_command('mv', str(old_path), str(new_path))


def _get_library():
    papers = {}
    for dir_path, _, file_names in walk(LIBRARY_DIR):
        for name in file_names:
            path = Path(dir_path, name)
            if path.suffix == '.pdf':
                papers[path.stem] = path
    return papers


def _run_shell_command(command, *args, capture_output=False, verbose=True):
    if verbose:
        print(command + ' ' + ' '.join(
            (arg if arg.startswith('-') else f'"{arg}"')
            for arg in args
        ))
    return run([command, *args], capture_output=capture_output)


def _yield_all_attributes(*attributes, filter_fn=None):
    for entry in read_library().values():
        if filter_fn and not filter_fn(entry):
            continue
        for role in attributes:
            if role in entry:
                yield entry[role]


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


def read_library(use_cache=True):
    if use_cache and BIBTEX_CACHE_PATH.exists() and getmtime(BIBTEX_CACHE_PATH) > getmtime(BIBTEX_PATH):
        with BIBTEX_CACHE_PATH.open() as fd:
            library = literal_eval(fd.read())
    else:
        makedirs(BIBTEX_CACHE_PATH.parent, exist_ok=True)
        library = PARSER.parse_file(BIBTEX_PATH)
        with BIBTEX_CACHE_PATH.open('w') as fd:
            fd.write(repr(library))
    tags = _read_tags()
    for paper_id, paper_tags in tags.items():
        if paper_id in library:
            library[paper_id]['tags'] = paper_tags
    return library


# main actions


def do_read(*filepaths):
    for filepath in filepaths:
        _store(filepath)


def do_tag(filepath, *tags):
    _store(filepath)
    with open(TAGS_PATH, 'a') as fd:
        fd.write(' '.join([filepath.stem, *tags]) + '\n')


def do_lint():
    entries = read_library()
    # check for non "last, first" authors and editors
    for entry_id, entry in entries.items():
        for attribute in ['author', 'editor']:
            if attribute not in entry:
                continue
            if entry[attribute] in WEIRD_NAMES:
                continue
            people = entry[attribute].split(' and ')
            if any((',' not in person) for person in people if person not in WEIRD_NAMES):
                print(f'non-conforming {attribute}s in {entry_id}:')
                print(f'    current:')
                print(f'        {attribute} = {{{entry[attribute]}}},')
                pattern = '(?P<first>[A-Z][^ ]*( [A-Z][^ ]*)*) (?P<last>.*)'
                suggestion = ' and '.join([
                    person if person in WEIRD_NAMES
                    else re.sub(
                        pattern,
                        (lambda match: match.group('last') + ', ' + match.group('first')),
                        person)
                    for person in people
                ])
                print(f'    suggested:')
                print(f'        {attribute} = {{{suggestion}}},')
    # check for incorrectly-formed IDs
    for current_id, entry in entries.items():
        if entry['author'] in WEIRD_NAMES:
            first_author = WEIRD_NAMES[entry['author']]
        else:
            first_author = entry['author'].split(' and ')[0]
            first_author = WEIRD_NAMES.get(first_author, first_author.split(',')[0])
        entry_id = first_author + entry['year'] + entry['title']
        entry_id = re.sub(r'\\.{(.)}', r'\1', entry_id)
        entry_id = re.sub('[^0-9A-Za-z]', '', entry_id)
        current_id = current_id
        while any(re.search(suffix + '$', current_id) for suffix in ID_SUFFIXES):
            for suffix in ID_SUFFIXES:
                current_id = re.sub(suffix + '$', '', current_id)
        if not entry_id.lower().startswith(current_id.lower()):
            print(f'suspicious ID: {current_id.lower()} vs {entry_id.lower()}')
            print(f'    Current: {current_id.lower()}')
            print(f'    Computed: {entry_id.lower()}')
    # make sure all files in the library have an entry
    library = _get_library()
    for key in set(library.keys()) - set(entries.keys()):
        print('missing entry for file {}'.format(library[key]))
    # make sure all unusual words are quoted
    for entry_id, entry in entries.items():
        title = entry['title']
        changed = True
        while changed:
            changed = False
            if re.search('{[^{}]*}', title):
                title = re.sub('{[^{}]*}', '', title)
                changed = True
        for word in title.split():
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


def do_organizations():
    for organization in _yield_all_attributes('institution', 'school'):
        print(organization)


def do_publishers():
    for publisher in _yield_all_attributes('publisher'):
        print(publisher)


def do_journals():
    for journal in _yield_all_attributes('journal'):
        print(journal)


def do_conferences():
    generator = _yield_all_attributes(
        'booktitle',
        filter_fn=(lambda entry: entry['type'] == 'inproceedings'),
    )
    for conference in generator:
        print(conference)


def do_people():
    for people in _yield_all_attributes('author', 'editor'):
        for person in people.split(' and '):
            print(person)


def do_tags():
    tags = set.union(*(_read_tags().values()))
    for tag in sorted(tags, key=str.lower):
        print(tag)


def do_index():
    index_path = LIBRARY_DIR.joinpath('index.html')
    with open(index_path, 'w') as fd:
        fd.write('<pre>\n')
        for entry_id, entry in sorted(read_library().items()):
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


def do_sync():
    do_pull()
    do_index()
    do_push()


def do_diff():
    md5_args = find_md5()
    local_output = _run_shell_command(
        'find',
        str(LIBRARY_DIR),
        '-name', '*.pdf',
        '-exec', *md5_args, '{}', ';',
        capture_output=True,
        verbose=False,
    )
    remote_output = _run_shell_command(
        'ssh',
        REMOTE_HOST,
        f"find {REMOTE_PATH} -name '*.pdf' -exec md5sum '{{}}' ';'",
        capture_output=True,
        verbose=False,
    )
    hashes = defaultdict(dict)
    for location, output in zip(('local', 'remote'), (local_output, remote_output)):
        for line in output.stdout.decode('utf-8').splitlines():
            md5_hash, path = line.split()
            hashes[Path(path).stem][location] = md5_hash
    lines = {}
    for stem, file_hashes in hashes.items():
        if 'local' not in file_hashes:
            lines[stem] = '>'
        elif 'remote' not in file_hashes:
            lines[stem] = '<'
        elif file_hashes['local'] != file_hashes['remote']:
            lines[stem] = '!'
    for stem, symbol in sorted(lines.items()):
        print(f'{symbol} {stem}')


def do_push():
    _run_shell_command(
        'rsync',
        '--archive',
        '--progress',
        '--rsh=ssh',
        '--exclude', '.*',
        f'{LIBRARY_DIR}/',
        f'{REMOTE_HOST}:{REMOTE_PATH}',
    )


def do_pull():
    _run_shell_command(
        'rsync',
        '--archive',
        '--progress',
        '--rsh=ssh',
        '--exclude', '.*',
        f'{REMOTE_HOST}:{REMOTE_PATH}/',
        str(LIBRARY_DIR),
    )


def do_url(*filepaths):
    for filepath in filepaths:
        print(_get_url(filepath))


def do_remove(*filepaths):
    for filepath in filepaths:
        filepath = Path(filepath)
        filename = filepath.stem + '.pdf'
        local_path = LIBRARY_DIR.joinpath(filepath.stem[0].lower(), filename)
        remote_path = REMOTE_PATH.joinpath(filepath.stem[0].lower(), filename)
        _run_shell_command('ssh', REMOTE_HOST, f"rm -vf '{remote_path}'")
        _run_shell_command('rm', '-vf', str(local_path))


if __name__ == '__main__':
    main()
