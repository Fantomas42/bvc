"""Command line for finding unused pinned versions"""
import logging
import sys
from argparse import ArgumentParser

from bvc.checker import UnusedVersionsChecker
from bvc.configparser import VersionsConfigParser
from bvc.logger import logger


def cmdline(argv=sys.argv[1:]):
    parser = ArgumentParser(
        description='Find unused pinned eggs'
    )
    parser.add_argument(
        'source',
        default='versions.cfg',
        nargs='?',
        help='The file where versions are pinned '
        '(default: versions.cfg)'
    )

    filter_group = parser.add_argument_group('Filtering')
    filter_group.add_argument(
        '--eggs',
        dest='eggs',
        default='./eggs/',
        help='The directory where the eggs are located '
        '(default: ./eggs/)'
    )
    filter_group.add_argument(
        '-e', '--exclude',
        action='append',
        dest='excludes',
        default=[],
        help='Exclude package when checking updates '
        '(can be used multiple times)'
    )

    file_group = parser.add_argument_group('File')
    file_group.add_argument(
        '-w', '--write',
        action='store_true',
        dest='write',
        default=False,
        help='Write the updates in the source file'
    )
    file_group.add_argument(
        '--indent',
        dest='indentation',
        type=int,
        default=-1,
        help='Spaces used when indenting "key = value" (default: auto)'
    )
    file_group.add_argument(
        '--sorting',
        dest='sorting',
        default='',
        choices=['alpha', 'ascii', 'length'],
        help='Sorting algorithm used on the keys when writing source file '
        '(default: None)'
    )

    verbosity_group = parser.add_argument_group('Verbosity')
    verbosity_group.add_argument(
        '-v',
        action='count',
        dest='verbosity',
        default=1,
        help='Increase verbosity (specify multiple times for more)'
    )
    verbosity_group.add_argument(
        '-q',
        action='count',
        dest='quietly',
        default=0,
        help='Decrease verbosity (specify multiple times for more)'
    )

    if isinstance(argv, str):
        argv = argv.split()
    options = parser.parse_args(argv)

    verbose_logs = {
        0: 100,
        1: logging.WARNING,
        2: logging.INFO,
        3: logging.DEBUG
    }
    verbosity = min(3, max(0, options.verbosity - options.quietly))
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(verbose_logs[verbosity])
    logger.addHandler(console)

    source = options.source
    try:
        checker = UnusedVersionsChecker(
            source, options.eggs, options.excludes)
    except Exception as e:
        sys.exit(str(e))

    if not checker.unused:
        sys.exit(0)

    for package in checker.unused:
        logger.warning('- %s is unused.', package)

    if options.write:
        config = VersionsConfigParser(
            indentation=options.indentation,
            sorting=options.sorting
        )
        config.read(source)
        for package in checker.unused:
            config.remove_option('versions', package)

        config.write(source)
        logger.info('- %s updated.', source)

    sys.exit(0)
