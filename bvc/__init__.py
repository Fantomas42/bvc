"""Buildout version checker"""
import futures

import sys
import logging
from xmlrpclib import ServerProxy
from argparse import ArgumentParser
from collections import OrderedDict
from ConfigParser import NoSectionError
from ConfigParser import RawConfigParser
from distutils.version import LooseVersion

logger = logging.getLogger(__name__)


class VersionsConfigParser(RawConfigParser):
    """
    ConfigParser customized to read and write
    beautiful buildout files.
    """
    optionxform = str
    indentation = 24

    def write_section(self, fd, section):
        """
        Write a section of an .ini-format
        and all the keys within.
        """
        fd.write('[%s]\n' % section)
        for key, value in self._sections[section].items():
            if key != '__name__':
                if value is None:
                    value = ''
                fd.write('%s= %s\n' % (
                    key.ljust(self.indentation),
                    str(value).replace(
                        '\n', '\n'.ljust(self.indentation + 3))))

    def write(self, source):
        """
        Write an .ini-format representation of the
        configuration state with a readable indentation.
        """
        with open(source, 'wb') as fd:
            sections = self._sections.keys()
            for section in sections[:-1]:
                self.write_section(fd, section)
                fd.write('\n')
            self.write_section(fd, sections[-1])


class VersionsChecker(object):
    """
    Checks updates of packages from a config file on Pypi.
    """
    default_version = '0.0.0'

    def __init__(self, source, includes=[], excludes=[],
                 service_url='http://pypi.python.org/pypi',
                 threads=10):
        """
        Parses a config file containing pinned versions
        of eggs and check available updates.
        """
        self.source = source
        self.includes = includes
        self.excludes = excludes
        self.threads = threads
        self.service_url = service_url
        self.source_versions = OrderedDict(
            self.parse_versions(self.source))
        self.versions = self.include_exclude_versions(
            self.source_versions, self.includes, self.excludes)
        self.last_versions = OrderedDict(
            self.fetch_last_versions(self.versions.keys(),
                                     self.threads,
                                     self.service_url))
        self.updates = OrderedDict(self.find_updates(
            self.versions, self.last_versions))

    def parse_versions(self, source):
        """
        Parses the source file to return the packages
        with their current versions.
        """
        config = VersionsConfigParser()
        config.read(source)
        try:
            versions = config.items('versions')
        except NoSectionError:
            logger.debug("'versions' section not found in %s." % source)
            return []
        logger.info('- %d versions found in %s.' % (len(versions), source))
        return versions

    def include_exclude_versions(self, source_versions,
                                 includes=[], excludes=[]):
        """
        Includes and excludes packages to be checked in
        the default dict of packages with versions.
        """
        versions = source_versions.copy()
        packages_lower = map(lambda x: x.lower(), versions.keys())
        for include in includes:
            if include.lower() not in packages_lower:
                versions[include] = self.default_version
        excludes_lower = map(lambda x: x.lower(), excludes)
        for package in versions.keys():
            if package.lower() in excludes_lower:
                del versions[package]
        logger.info('- %d packages need to be checked for updates.' %
                    len(versions))
        return versions

    def fetch_last_versions(self, packages, threads, service_url):
        """
        Fetch the latest versions of a list of packages,
        in a threaded manner or not.
        """
        versions = []
        if threads > 1:
            with futures.ThreadPoolExecutor(
                    max_workers=threads) as executor:
                tasks = [executor.submit(self.fetch_last_version,
                                         package, service_url)
                         for package in packages]
                for task in futures.as_completed(tasks):
                    versions.append(task.result())
        else:
            for package in packages:
                versions.append(self.fetch_last_version(
                    package, service_url))
        return versions

    def fetch_last_version(self, package, service_url):
        """
        Fetch the last version of a package on Pypi.
        """
        package_key = package.lower()
        max_version = self.default_version
        logger.info('> Fetching latest datas for %s...' % package)
        client = ServerProxy(service_url)
        results = client.search({'name': package})
        for result in results:
            if result['name'].lower() == package_key:
                if LooseVersion(result['version']) > LooseVersion(max_version):
                    max_version = result['version']
        logger.debug('-> Last version of %s is %s.' % (package, max_version))
        return (package, max_version)

    def find_updates(self, versions, last_versions):
        """
        Compare the current versions of the packages
        with the last versions to find updates.
        """
        updates = []
        for package, current_version in versions.items():
            last_version = last_versions[package]
            if last_version != current_version:
                logger.debug(
                    '=> %s current version (%s) and last '
                    'version (%s) are different.' %
                    (package, current_version, last_version))
                updates.append((package, last_version))
        logger.info('- %d package updates found.' % len(updates))
        return updates


def cmdline(argv=None):
    parser = ArgumentParser(
        description='Check availables updates from a '
        'version section of a buildout script')
    parser.add_argument(
        '-s', '--source', dest='source',
        help='The file where versions are pinned '
        '(default: versions.cfg)', default='versions.cfg')
    parser.add_argument(
        '-i', '--include', action='append', dest='includes',
        help='Include package when checking updates'
        ' (can be used multiple times)', default=[]),
    parser.add_argument(
        '-e', '--exclude', action='append', dest='excludes',
        help='Exclude package when checking updates'
        ' (can be used multiple times)', default=[]),
    parser.add_argument(
        '-t', '--threads', dest='threads', type=int,
        help='Threads used for checking the versions in parallel',
        default=10)
    parser.add_argument(
        '-w', '--write', action='store_true', dest='write',
        help='Write the updates in the source file',
        default=False)
    parser.add_argument(
        '--indent', dest='indentation', type=int,
        help='Spaces used when indenting "key = value" (default: 24)',
        default=24)
    parser.add_argument(
        '--service-url',  dest='service_url',
        help='The service to use for checking the packages',
        default='http://pypi.python.org/pypi')
    parser.add_argument(
        '-v', action='count', dest='verbosity',
        help='Increase verbosity (specify multiple times for more)')

    if isinstance(argv, basestring):
        argv = argv.split()
    else:
        argv = sys.argv[1:]
    options = parser.parse_args(argv)

    verbosity = options.verbosity
    if verbosity:
        console = logging.StreamHandler(sys.stdout)
        logger.addHandler(console)
        logger.setLevel(verbosity >= 2 and
                        logging.DEBUG or logging.INFO)

    source = options.source
    try:
        checker = VersionsChecker(
            source, options.includes, options.excludes,
            options.service_url, options.threads)
    except Exception as e:
        sys.exit(e.message or str(e))

    if not checker.updates:
        sys.exit(0)

    if options.write:
        config = VersionsConfigParser()
        config.indentation = options.indentation
        config.read(source)
        if not config.has_section('versions'):
            config.add_section('versions')
        for package, version in checker.updates.items():
            config.set('versions', package, version)
        config.write(source)
        logger.info('- %s updated.' % source)
    else:
        print('[versions]')
        for package, version in checker.updates.items():
            print('%s= %s' % (package.ljust(options.indentation), version))

    sys.exit(0)


if __name__ == '__main__':
    cmdline()
