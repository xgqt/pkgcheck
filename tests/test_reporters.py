import json
import sys
from functools import partial
from textwrap import dedent

import pytest
from pkgcheck import base, reporters
from pkgcheck.checks import git, metadata, metadata_xml, pkgdir, profiles
from pkgcore.test.misc import FakePkg
from snakeoil.formatters import PlainTextFormatter


class BaseReporter:

    reporter_cls = reporters.Reporter

    @pytest.fixture(autouse=True)
    def _setup(self):
        self.log_warning = profiles.ProfileWarning(Exception('profile warning'))
        self.log_error = profiles.ProfileError(Exception('profile error'))
        pkg = FakePkg('dev-libs/foo-0')
        self.commit_result = git.InvalidCommitMessage('no commit message', commit='8d86269bb4c7')
        self.category_result = metadata_xml.CatMissingMetadataXml('metadata.xml', pkg=pkg)
        self.package_result = pkgdir.InvalidPN(('bar', 'baz'), pkg=pkg)
        self.versioned_result = metadata.BadFilename(('0.tar.gz', 'foo.tar.gz'), pkg=pkg)

    def mk_reporter(self, **kwargs):
        out = PlainTextFormatter(sys.stdout)
        return self.reporter_cls(out, **kwargs)

    add_report_output = None

    def test_add_report(self, capsys):
        with self.mk_reporter() as reporter:
            reporter.report(self.commit_result)
            reporter.report(self.log_warning)
            reporter.report(self.category_result)
            reporter.report(self.package_result)
            reporter.report(self.versioned_result)
        out, err = capsys.readouterr()
        assert not err
        assert out == self.add_report_output


class TestStrReporter(BaseReporter):

    reporter_cls = reporters.StrReporter
    add_report_output = dedent("""\
        commit 8d86269bb4c7: no commit message
        profile warning
        dev-libs: category is missing metadata.xml
        dev-libs/foo: invalid package names: [ bar, baz ]
        dev-libs/foo-0: bad filenames: [ 0.tar.gz, foo.tar.gz ]
    """)


class TestFancyReporter(BaseReporter):

    reporter_cls = reporters.FancyReporter
    add_report_output = dedent("""\
        commit
          InvalidCommitMessage: commit 8d86269bb4c7: no commit message

        profiles
          ProfileWarning: profile warning

        dev-libs
          CatMissingMetadataXml: category is missing metadata.xml

        dev-libs/foo
          InvalidPN: invalid package names: [ bar, baz ]
          BadFilename: version 0: bad filenames: [ 0.tar.gz, foo.tar.gz ]
    """)


class TestJsonReporter(BaseReporter):

    reporter_cls = reporters.JsonReporter
    add_report_output = dedent("""\
        {"_style": {"InvalidCommitMessage": "commit 8d86269bb4c7: no commit message"}}
        {"_warning": {"ProfileWarning": "profile warning"}}
        {"dev-libs": {"_error": {"CatMissingMetadataXml": "category is missing metadata.xml"}}}
        {"dev-libs": {"foo": {"_error": {"InvalidPN": "invalid package names: [ bar, baz ]"}}}}
        {"dev-libs": {"foo": {"0": {"_warning": {"BadFilename": "bad filenames: [ 0.tar.gz, foo.tar.gz ]"}}}}}
    """)


class TestXmlReporter(BaseReporter):

    reporter_cls = reporters.XmlReporter
    add_report_output = dedent("""\
        <checks>
        <result><class>InvalidCommitMessage</class><msg>commit 8d86269bb4c7: no commit message</msg></result>
        <result><class>ProfileWarning</class><msg>profile warning</msg></result>
        <result><category>dev-libs</category><class>CatMissingMetadataXml</class><msg>category is missing metadata.xml</msg></result>
        <result><category>dev-libs</category><package>foo</package><class>InvalidPN</class><msg>invalid package names: [ bar, baz ]</msg></result>
        <result><category>dev-libs</category><package>foo</package><version>0</version><class>BadFilename</class><msg>bad filenames: [ 0.tar.gz, foo.tar.gz ]</msg></result>
        </checks>
    """)


class TestCsvReporter(BaseReporter):

    reporter_cls = reporters.CsvReporter
    add_report_output = dedent("""\
        ,,,commit 8d86269bb4c7: no commit message
        ,,,profile warning
        dev-libs,,,category is missing metadata.xml
        dev-libs,foo,,"invalid package names: [ bar, baz ]"
        dev-libs,foo,0,"bad filenames: [ 0.tar.gz, foo.tar.gz ]"
    """)


class TestFormatReporter(BaseReporter):

    reporter_cls = partial(reporters.FormatReporter, '')

    def test_add_report(self, capsys):
        for format_str, expected in (
                    ('r', 'r\n' * 5),
                    ('{category}', 'dev-libs\n' * 3),
                    ('{category}/{package}', '/\n/\ndev-libs/\n' + 'dev-libs/foo\n' * 2),
                    ('{category}/{package}-{version}', '/-\n/-\ndev-libs/-\ndev-libs/foo-\ndev-libs/foo-0\n'),
                    ('{name}',
                     'InvalidCommitMessage\nProfileWarning\nCatMissingMetadataXml\nInvalidPN\nBadFilename\n'),
                    ('{foo}', ''),
                ):
            self.reporter_cls = partial(reporters.FormatReporter, format_str)
            self.add_report_output = expected
            super().test_add_report(capsys)

    def test_unsupported_index(self, capsys):
        self.reporter_cls = partial(reporters.FormatReporter, '{0}')
        with self.mk_reporter() as reporter:
            with pytest.raises(base.PkgcheckUserException) as excinfo:
                reporter.report(self.versioned_result)
            assert 'integer indexes are not supported' in str(excinfo.value)


class TestJsonStream(BaseReporter):

    reporter_cls = reporters.JsonStream

    def test_add_report(self, capsys):
        with self.mk_reporter() as reporter:
            for result in (
                    self.log_warning, self.log_error, self.commit_result,
                    self.category_result, self.package_result, self.versioned_result):
                reporter.report(result)
                out, err = capsys.readouterr()
                assert not err
                deserialized_result = next(reporter.from_iter([out]))
                assert str(deserialized_result) == str(result)

    def test_deserialize_error(self):
        with self.mk_reporter() as reporter:
            # deserializing non-result objects raises exception
            obj = reporter.to_json(['result'])
            with pytest.raises(reporters.DeserializationError, match='failed loading'):
                next(reporter.from_iter([obj]))

            # deserializing mangled JSON result objects raises exception
            obj = reporter.to_json(self.versioned_result)
            del obj['__class__']
            json_obj = json.dumps(obj)
            with pytest.raises(reporters.DeserializationError, match='unknown result'):
                next(reporter.from_iter([json_obj]))
