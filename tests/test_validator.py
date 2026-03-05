import pytest

from validation.validator import Validator


def test_validate_with_missing_fields(tmp_path, caplog):
    config = {}
    workspace = tmp_path
    validator = Validator(config, workspace, telemetry=None)

    finding = {'title': 'Test', 'severity': 'HIGH'}
    result = validator.validate(finding)

    assert result['severity'] == 'high'
    assert result['location'] == 'N/A'
    assert result['description'] == 'No description provided.'
    assert not result['validated']  # missing description


def test_deduplicate_removes_duplicates(tmp_path):
    config = {}
    validator = Validator(config, tmp_path, telemetry=None)

    f1 = {'title': 'Bug', 'location': 'http://foo', 'payload': 'x'}
    f2 = {'title': 'Bug', 'location': 'http://foo', 'payload': 'x'}
    f3 = {'title': 'Bug', 'location': 'http://foo', 'payload': 'y'}
    unique = validator.deduplicate([f1, f2, f3])
    assert len(unique) == 2


def test_deduplicate_when_no_findings(tmp_path):
    validator = Validator({}, tmp_path, telemetry=None)
    assert validator.deduplicate([]) == []
